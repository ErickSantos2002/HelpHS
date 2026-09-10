"""
De saída do modelo para vetor — o passo que erra em silêncio.

O modelo não devolve um vetor por texto. Ele devolve um vetor POR TOKEN:
`(textos, tokens, 1024)`. Transformar isso em um vetor por texto é o pooling, e
é trabalho de quem chama o modelo, não do modelo.

POR QUE ISTO MERECE UM ARQUIVO E UM TESTE
------------------------------------------
Porque as três formas de errar aqui produzem vetores perfeitamente válidos:
mesma dimensão, mesmo tipo, sem exceção nenhuma. O `INSERT` aceita, a busca
roda, a Helô responde — e responde pior, sem que nada acuse. É a mesma classe
do redator de senha: falha sem ruído.

As três formas:

1. **Ignorar a máscara de atenção.** O lote é preenchido até o comprimento do
   texto mais longo, e os tokens de preenchimento entram na média como se
   fossem conteúdo. O estrago é proporcional ao preenchimento: medido, a
   pergunta curta do cliente num lote com um trecho longo desloca 0,133 de
   distância de cosseno — dezessete vezes o ruído de arredondamento.

2. **Pegar só o primeiro token (CLS).** Funciona em modelos treinados para
   isso; o `bge-m3` é treinado para média. Medido, muda a distância do par
   conhecido de 0,25 para 0,45.

3. **Não normalizar.** Este NÃO afeta a distância de cosseno — foi medido, dá
   exatamente o mesmo número, porque o cosseno normaliza por dentro. Continua
   valendo a pena: com o vetor normalizado, trocar o operador da busca para
   distância L2 ou produto interno preserva a ordem. Sem normalizar, não
   preserva. É seguro contra uma mudança futura, não contra a de hoje.
"""

import numpy as np


def agrupa(tokens: np.ndarray, mascara: np.ndarray) -> np.ndarray:
    """
    Média dos tokens REAIS de cada texto, normalizada.

    Args:
        tokens: `(textos, tokens, dim)` — a saída crua do modelo.
        mascara: `(textos, tokens)` — 1 no token real, 0 no preenchimento.

    Returns:
        `(textos, dim)`, cada linha com norma 1.
    """
    if tokens.ndim != 3:
        raise ValueError(f"esperava (textos, tokens, dim), veio {tokens.shape}")
    if mascara.shape != tokens.shape[:2]:
        raise ValueError(f"máscara {mascara.shape} não casa com tokens {tokens.shape}")

    m = mascara.astype(np.float32)[:, :, None]
    reais = m.sum(axis=1)
    if (reais == 0).any():
        raise ValueError("texto sem nenhum token real na máscara")

    # A máscara zera o preenchimento ANTES da soma. É ela que faz o trabalho.
    #
    # O divisor é a contagem de tokens reais porque é a definição de média — e
    # NÃO porque o resultado dependa disso. Medido por mutação: dividir pelo
    # comprimento do lote dá exatamente o mesmo vetor final, porque a diferença
    # é um fator de escala e a normalização logo abaixo o apaga. Fica registrado
    # para ninguém "consertar" isto achando que achou um defeito, e para ninguém
    # gastar teste tentando prender uma diferença que não existe.
    #
    # Só voltaria a importar se a normalização saísse — e ela tem teste próprio.
    media = (tokens.astype(np.float32) * m).sum(axis=1) / reais

    normas = np.linalg.norm(media, axis=1, keepdims=True)
    normas[normas == 0] = 1.0
    return media / normas
