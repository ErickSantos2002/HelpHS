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
        Até `k` trechos, do mais próximo ao mais distante. Lista VAZIA quando o
        chamado não tem produto — ver abaixo.
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
