"""
A busca na base de manuais da Helô — e os dois filtros que não são opcionais.

Este módulo é a ÚNICA porta para os trechos. Não existe função aqui que
devolva trecho sem filtrar, e é de propósito: um filtro que se pode esquecer é
um filtro que vai ser esquecido, e o esquecimento não aparece como erro — sai
como resposta errada, com a fonte citada, na tela de quem opera um instrumento
de medição legal.

OS DOIS FILTROS

**Produto.** Todos os manuais falam de sopro, LED, bocal e calibração. Sem o
filtro, a busca vetorial traz o trecho do Phoebus para quem tem um Titan na
mão, porque os textos se parecem — é justamente onde ela é mais parecida que
ela mais erra.

**Tipo.** Só `tecnico`. Cinco dos oito documentos são fichas de venda, com
preço de aparelho e de calibração; a Helô cotando equipamento para quem abriu
chamado técnico é o pior resultado desta fase.

E o filtro de tipo tem uma segunda função, que é a que custa caro se faltar. O
**iBlow 10 Pro é o único produto com dois documentos** — a ficha comercial e o
manual técnico — e é exatamente o par que se contradiz: a ficha diz que o
aparelho pareia com o "Health App", o manual diz "i-SOBER". Sem o filtro de
tipo, os dois trechos entram na mesma recuperação, o modelo escolhe um, e a
Helô responde "Health App" CITANDO A FICHA COMERCIAL como fonte. Fonte errada é
pior do que fonte nenhuma, porque parece conferível.

Por isso os dois filtros têm a mesma força: não há parâmetro para desligar
nenhum dos dois, e não há caminho alternativo até a tabela.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    HeloChunk,
    HeloDocType,
    HeloDocument,
    Ticket,
    helo_chunk_products,
)

# Quantos trechos vão para o contexto do modelo. Quatro é o teto do que cabe
# num prompt sem afogar a pergunta: a base inteira tem 74 trechos, e as seções
# são curtas (a maior tem mil caracteres). Mais do que isso passa a competir
# com o próprio enunciado do cliente pela atenção do modelo.
K_TRECHOS = 4

# Distância máxima de cosseno para um trecho ser considerado pertinente.
#
# ESTE NÚMERO FOI MEDIDO, não escolhido. Em 09/09/2026, contra o corpus real
# (74 trechos, 3 manuais técnicos), com 40 perguntas rotuladas à mão: 27 com
# resposta conhecida no manual do produto e 13 sem resposta nenhuma lá dentro
# (preço, certificado RBC, dano físico, nota fiscal, e função que aquele
# aparelho não tem). As duas populações medidas no 1º colocado:
#
#     com resposta   n=27  mediana 0,2185   máximo 0,2850
#     sem resposta   n=13  mínimo   0,2590  mediana 0,2789
#
# 0,25 é o maior corte que ainda barra 100% das perguntas sem resposta.
# Preserva 22 das 27 com resposta (81%), e derruba os trechos de enchimento
# das que ficam: dos 160 trechos que hoje chegam ao modelo nessas 40
# perguntas, passam a chegar 25. Em 74% das perguntas com resposta sobra
# exatamente UM trecho — o certo — no lugar de um mais três de ruído.
#
# ONDE ISTO É FRÁGIL, e por que está escrito aqui e não só no commit:
#
# 1. A margem é de 0,009 (0,25 contra 0,2590, que é "quanto custa a calibração
#    do titan" casando com "2. Composição Física"). É um ajuste a 40 pontos,
#    não uma lei — e as perguntas foram escritas por quem já sabia a resposta.
#    O `test_helo_pooling_postgres.py` mostra, com embedding real, um ACERTO a
#    0,2533: as duas populações se sobrepõem entre 0,25 e 0,26. Este corte não
#    separa duas nuvens, escolhe um lado da sobreposição — o apertado, porque
#    cortar acerto custa uma escalada e passar trecho errado custa uma
#    instrução errada.
# 2. Foi medido com TRÊS manuais. Espaço mais denso encurta distância; quando
#    houver manual para mais produtos, isto se remede junto com a dívida do
#    trecho genérico.
# 3. O número vale para o bge-m3 e para estes textos. Trocar de modelo de
#    embedding invalida a medição inteira, sem que nada quebre visivelmente.
# 3b. **A população "tem resposta" está enviesada para o fácil.** As 27
#    perguntas foram escritas por quem já tinha lido os manuais, então elas
#    usam as palavras do manual. Cliente de verdade escreve "não sai nada no
#    visor", não "como interpreto os resultados" — e distância só cresce com
#    essa diferença. Quem revisitar o 0,25 precisa saber que os 27 não
#    representam cliente nenhum: representam o melhor caso. O número real de
#    acertos preservados em produção é MENOR que os 81% medidos aqui, e a
#    forma de descobrir quanto é medir com pergunta de cliente de verdade,
#    quando houver conversa gravada para isso.
# 4. As 5 perguntas com resposta que o corte derruba viram escalada. É o lado
#    barato de errar: um humano responde. O outro lado é a Helô ditar
#    procedimento de instrumento de medição legal a partir do trecho errado.
#
# A borda em si (`<=` contra `<`) NÃO está presa por teste, e de propósito: a
# distância vem em ponto flutuante do pgvector e nunca cai exatamente em 0,25.
# Um teste da igualdade exata seria instável, e a mutação que troca o operador
# sobrevive — medido, não suposto.
TETO_DE_DISTANCIA = 0.25

# A string que o bloco de contexto recebe quando a busca não achou nada.
#
# Literal, e nunca um bloco vazio. Bloco vazio o modelo interpreta como "não
# recebi contexto" e responde do próprio bolso, que é exatamente o que a Fase 2
# existe para impedir. A string explícita casa com a regra do prompt e produz
# escalada.
NADA_ENCONTRADO = "NADA ENCONTRADO"


@dataclass(frozen=True)
class TrechoRecuperado:
    """Um trecho e a fonte dele, porque a resposta cita."""

    secao: str
    conteudo: str
    documento: str
    exige_credencial_admin: bool
    distancia: float


async def busca_trechos(
    db: AsyncSession,
    ticket: Ticket,
    vetor: Sequence[float],
    k: int = K_TRECHOS,
) -> list[TrechoRecuperado]:
    """
    Os trechos técnicos do produto DESTE chamado, mais próximos do vetor.

    Args:
        ticket: o chamado — dele saem o produto e, portanto, o filtro. Recebe o
            chamado inteiro, e não um `product_id` solto, para que não exista
            um jeito de chamar esta função sobre um produto que não é o dele.
        vetor: o embedding da pergunta do cliente.

    Returns:
        Até `k` trechos, do mais próximo ao mais distante, e nenhum além de
        `TETO_DE_DISTANCIA`. Lista VAZIA quando o chamado não tem produto, e
        também quando tudo ficou longe demais — os dois casos desembocam no
        mesmo `NADA ENCONTRADO`, de propósito: um estado novo para "achei mas
        está longe" só daria ao modelo uma terceira coisa para interpretar
        errado.
    """
    # Chamado sem produto devolve nada, e isso é resposta, não omissão.
    #
    # `Ticket.product_id` é nulável: dá para abrir chamado sem escolher
    # aparelho. Sem produto não há como garantir que o procedimento é do
    # aparelho certo, e a alternativa — buscar em tudo — é a versão sem filtro
    # do defeito que este módulo existe para impedir. Nada encontrado faz a
    # Helô escalar, que é o comportamento certo para uma pergunta que ela não
    # tem como responder com segurança.
    if ticket.product_id is None:
        return []

    consulta = (
        select(
            HeloChunk.secao,
            HeloChunk.conteudo,
            HeloDocument.title,
            HeloChunk.exige_credencial_admin,
            HeloChunk.embedding.cosine_distance(vetor).label("distancia"),
        )
        .join(HeloDocument, HeloDocument.id == HeloChunk.document_id)
        .join(helo_chunk_products, helo_chunk_products.c.chunk_id == HeloChunk.id)
        .where(
            # Os dois filtros, lado a lado e sem condicional nenhuma em volta.
            helo_chunk_products.c.product_id == ticket.product_id,
            HeloDocument.doc_type == HeloDocType.tecnico,
            # Trecho ainda não embutido não tem como ser ordenado por
            # distância — e ordenar por NULL colocaria lixo no topo.
            HeloChunk.embedding.is_not(None),
            # O teto de distância. Sem ele a busca SEMPRE devolve os quatro
            # mais próximos, por mais longe que estejam: "como conecto na
            # impressora" num Titan, que não tem impressora, devolvia o passo
            # a passo de ligar o aparelho como se fosse resposta. O modelo
            # recebe esse trecho num bloco que o prompt chama de "sua única
            # fonte de verdade técnica".
            HeloChunk.embedding.cosine_distance(vetor) <= TETO_DE_DISTANCIA,
        )
        .order_by("distancia")
        .limit(k)
    )

    return [
        TrechoRecuperado(
            secao=secao,
            conteudo=conteudo,
            documento=documento,
            exige_credencial_admin=exige,
            distancia=float(distancia),
        )
        for secao, conteudo, documento, exige, distancia in (await db.execute(consulta)).all()
    ]


def monta_base_tecnica(trechos: list[TrechoRecuperado]) -> str:
    """
    O bloco BASE TÉCNICA que vai no prompt, com a fonte em cada trecho.

    A fonte não é enfeite: é o que permite ao cliente conferir, e é o que
    separa suporte de chute. Ela viaja com o trecho desde aqui para o modelo
    não precisar inventar de onde tirou.
    """
    if not trechos:
        return NADA_ENCONTRADO

    partes = [f"{len(trechos)} trechos recuperados, filtrados pelo produto do chamado.", ""]
    for numero, t in enumerate(trechos, start=1):
        partes.append(f"--- trecho {numero} ---")
        partes.append(f"Fonte: {t.documento}, {t.secao}")
        if t.exige_credencial_admin:
            # A marca viaja para o modelo em texto, e não como metadado: o que
            # ele lê é o que ele obedece. Sem a linha, ele entregaria o
            # procedimento e a escalada seria cega.
            partes.append(
                "ATENÇÃO: este procedimento exige senha de administrador, que você NÃO possui "
                "e NÃO pode fornecer. Escale dizendo exatamente isso."
            )
        partes.append(t.conteudo)
        partes.append("")
    return "\n".join(partes).strip()
