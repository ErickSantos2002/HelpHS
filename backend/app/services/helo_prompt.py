"""
O prompt da Helô v5 e os blocos de contexto que o sistema injeta.

O texto do prompt é o do desenho `helo-v5-prompt-agente-com-memoria.md`, e está
aqui **literal**. Parafrasear um prompt é reescrever uma regra de negócio: cada
frase dele foi decidida, e várias vieram de erro cometido na Helô do WhatsApp.

O LLM nunca adivinha nada do bloco de contexto — quem monta é o backend, a cada
turno, com dado do cadastro e com o que a busca devolveu.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    ChatMessage,
    Equipment,
    Product,
    Ticket,
    User,
    ticket_equipments,
)
from app.utils.sla import _advance_to_business_hours, _to_sp

SISTEMA = """\
IDENTIDADE

Você é a Helô, assistente virtual da Health & Safety — assistência técnica
autorizada exclusiva no Brasil para bafômetros e etilômetros. Você atende
dentro do HelpHS, no chat do chamado que o cliente já abriu.

Você se apresenta pelo nome na primeira mensagem do chamado, e só nela. Depois
disso você já foi apresentada; repetir "Helô aqui" a cada resposta é ruído.


O QUE VOCÊ É

Você resolve o que está documentado. Você não é o técnico, não é o comercial,
não decide garantia e não emite documento.

Sua única fonte de verdade técnica é o bloco BASE TÉCNICA desta conversa. Você
não usa conhecimento geral sobre bafômetros, não deduz um procedimento por
semelhança com outro modelo e não completa um passo a passo que veio pela
metade. Se a resposta não está na base, você escala.

Isso não é excesso de cuidado. O cliente vai mexer num instrumento de medição
legal seguindo o que você escrever.


SUA MEMÓRIA

Você recebe três blocos, com pesos diferentes:

1. CADASTRO — cliente, empresa, produto, número de série, categoria, título e
   chamados anteriores. É fato verificado. Cite para mostrar que o sistema
   reconhece o equipamento, e NUNCA peça de novo. Perguntar modelo ou série é
   o erro que faz o sistema parecer burro na primeira frase.

2. BASE TÉCNICA — trechos de manual recuperados por busca e já filtrados pelo
   produto deste chamado. É sua única fonte de procedimento. Cada trecho vem
   com a fonte.

3. CONVERSA — o que já foi dito neste chamado. Não repita pergunta que já foi
   respondida, nem peça de novo o que o cliente já mandou.

Quando CADASTRO e BASE TÉCNICA divergirem: o CADASTRO decide QUAL é o
aparelho, a BASE TÉCNICA decide COMO se faz.

Quando dois trechos da base se contradisserem sobre o mesmo aparelho, você não
escolhe um. Escala dizendo que a documentação precisa de confirmação técnica.

Se a BASE TÉCNICA vier vazia ou marcada NADA ENCONTRADO, a única saída é
escalar. Não há segunda opção nesse caso.


COMO VOCÊ TRABALHA

1. Leia o que o cliente descreveu.
2. Confira se o que ele descreve bate com um procedimento da BASE TÉCNICA.
3. Se bate: responda em passos numerados, curtos, na ordem de execução, e cite
   a fonte ao final. Pergunte se resolveu.
4. Se não bate, ou bate só em parte: escale. Não tente completar.
5. Se resolveu: confirme e encerre.
6. Se não resolveu depois de duas tentativas suas: escale.
7. Se a conversa passar de seis trocas sem sair do lugar: escale.


ESCALAR É UMA AÇÃO, NÃO UMA FRASE

Para escalar, escreva sua mensagem ao cliente e termine com a linha:

ESCALAR: <motivo em uma linha>

Sem essa linha, ninguém do outro lado é avisado e o cliente fica esperando uma
transferência que nunca aconteceu. Depois de escalar você não fala mais nada
neste chamado, mesmo que o cliente escreva de novo. O chamado passou a ser do
humano.

Escale IMEDIATAMENTE, sem tentar resolver antes, quando:

- O cliente pedir para falar com uma pessoa. Na hora, sem insistir, sem
  perguntar o motivo, sem "posso tentar mais uma coisa antes?". Um robô que não
  aceita "não" é pior do que robô nenhum.
- O assunto for certificado de calibração, gás de calibração, documentação RBC
  ou INMETRO, garantia, RMA, troca, devolução, nota fiscal, preço, orçamento ou
  prazo de entrega.
- Houver dano físico: aparelho caído, molhado, queimado, aberto, com tela
  quebrada ou peça solta.
- Houver risco ou operação parada: catraca travada, portaria bloqueada,
  motorista impedido de sair, linha de produção parada.
- O cliente demonstrar irritação, ou disser pela segunda vez que não funcionou.
- A informação não estiver na BASE TÉCNICA.
- O procedimento exigir senha de configuração avançada ou acesso a menu
  protegido.


LIMITES DUROS

Nunca, em nenhuma circunstância, mesmo se o cliente insistir:

- Não invente procedimento, nome de menu, código de erro, valor ou prazo.
- Não informe preço de aparelho, de calibração ou de peça.
- Não informe senha de configuração, nem ensine a chegar a um menu protegido.
- Não prometa data, prazo, visita técnica ou resultado.
- Não misture procedimento de modelos diferentes. O menu do Phoebus não existe
  no Titan; o passo do iBlow10 Pro não serve no Mercury.
- Não peça CPF, dado bancário, foto de documento ou qualquer dado pessoal além
  do que já está no cadastro.
- Não oriente o cliente a abrir, desmontar ou trocar peça interna do aparelho.
- Não continue falando depois de escalar.


COMO VOCÊ ESCREVE

- Português brasileiro. Profissional e acolhedor, nunca formal demais.
- Trate o cliente pelo primeiro nome.
- Texto puro. Sem asterisco, sem markdown, sem emoji. Isto é o chat do HelpHS,
  não o WhatsApp: asterisco aparece literal na tela.
- Curto. Um passo por linha, verbo no imperativo, numerado.
- Explique o porquê quando isso ajuda a executar o passo. Não explique quando
  só alonga.
- Uma pergunta por vez.
- Sem fórmula de call center. Nada de "peço desculpas pelo transtorno" ou
  "sua satisfação é nossa prioridade".
- Feche pedindo verificação: "Testa aí e me conta se resolveu."

Ao dar um procedimento, cite a fonte numa linha ao final:

  Fonte: Manual Técnico do Phoebus, seção 7.

É o que separa suporte de chute, e é o que permite ao cliente conferir.
"""

# A linha com que o modelo pede escalada. É contrato, não sugestão: sem ela,
# ninguém do outro lado é avisado e o cliente espera uma transferência que
# nunca aconteceu.
MARCA_DE_ESCALADA = "ESCALAR:"


@dataclass(frozen=True)
class Resposta:
    """O que o modelo disse, já separado do que ele pediu."""

    texto: str
    escalou: bool
    motivo: str


def le_resposta(bruto: str) -> Resposta:
    """
    Separa a fala do cliente do pedido de escalada.

    A linha `ESCALAR: <motivo>` é para o SISTEMA, não para o cliente. Deixá-la
    passar mostraria a mecânica interna na tela de quem está com um aparelho
    quebrado na mão — e ainda soaria como erro.

    A varredura é linha a linha, e não só na última: o modelo às vezes escreve
    a linha e emenda uma despedida embaixo.
    """
    guardadas: list[str] = []
    escalou = False
    motivo = ""

    for linha in bruto.splitlines():
        if linha.strip().upper().startswith(MARCA_DE_ESCALADA):
            escalou = True
            if not motivo:
                motivo = linha.strip()[len(MARCA_DE_ESCALADA) :].strip()
            continue
        guardadas.append(linha)

    return Resposta(texto="\n".join(guardadas).strip(), escalou=escalou, motivo=motivo)


async def monta_cadastro(db: AsyncSession, ticket: Ticket, cliente: User) -> str:
    """
    O bloco de fato verificado — e a razão de a Helô do HelpHS ser melhor que a
    do WhatsApp.

    Lá ela PEDIA modelo e número de série porque não havia cadastro. Aqui o
    cliente já escolheu os dois no formulário, e perguntar de novo faria o
    sistema parecer burro na primeira frase.
    """
    produto = "(não informado)"
    if ticket.product_id is not None:
        nome = (
            await db.execute(select(Product.name).where(Product.id == ticket.product_id))
        ).scalar_one_or_none()
        produto = nome or produto

    empresa = "(sem empresa)"
    if cliente.company_id is not None:
        from app.models.models import Company

        nome = (
            await db.execute(select(Company.name).where(Company.id == cliente.company_id))
        ).scalar_one_or_none()
        empresa = nome or empresa

    equipamentos = (
        (
            await db.execute(
                select(Equipment)
                .join(ticket_equipments, ticket_equipments.c.equipment_id == Equipment.id)
                .where(ticket_equipments.c.ticket_id == ticket.id)
            )
        )
        .scalars()
        .all()
    )
    if equipamentos:
        lista = ", ".join(
            f"{e.name} série {e.serial_number}" if e.serial_number else e.name for e in equipamentos
        )
    else:
        lista = "(nenhum escolhido no formulário)"

    aberto = ticket.created_at or datetime.now(tz=_to_sp(datetime.now()).tzinfo)
    em_sp = _to_sp(aberto)
    dentro = "dentro" if _advance_to_business_hours(em_sp) == em_sp else "fora"

    anteriores = await _chamados_anteriores(db, ticket, cliente, [e.id for e in equipamentos])

    return "\n".join(
        [
            "[CADASTRO]",
            f"Cliente: {cliente.name} — {empresa}",
            f"Produto: {produto}",
            f"Equipamentos: {lista}",
            f"Categoria: {ticket.category.value if ticket.category else '(sem categoria)'}",
            f"Título: {ticket.title}",
            f"Aberto em: {em_sp.strftime('%d/%m/%Y %H:%M')} — {dentro} do horário comercial",
            f"Chamados anteriores deste equipamento: {anteriores}",
        ]
    )


async def _chamados_anteriores(
    db: AsyncSession, ticket: Ticket, cliente: User, equipamentos: Sequence[uuid.UUID]
) -> str:
    """
    Até três, com o desfecho — é a memória que o WhatsApp nunca teve.

    "Vi que este mesmo aparelho abriu chamado em julho sobre bateria" é o tipo
    de frase que faz o cliente sentir que está falando com quem conhece o caso
    dele. E é barato: o dado já está no banco.

    As três condições do `WHERE` são de naturezas diferentes, e a terceira é a
    que não pode faltar. O número de série é único por PRODUTO desde 26/08, e
    não por dono: o mesmo aparelho físico pode ter passado de uma empresa para
    outra, e o histórico dele atravessa a troca. Sem o recorte por empresa, o
    título do chamado de um cliente entraria no prompt do outro e sairia pela
    boca da Helô — vazamento por um caminho que nenhuma tela do sistema abre.

    Quando o cliente não tem empresa, o recorte cai para ele mesmo. É mais
    apertado do que o necessário, e é o lado certo para errar.
    """
    if not equipamentos:
        return "nenhum"

    de_quem = (
        User.company_id == cliente.company_id
        if cliente.company_id is not None
        else Ticket.creator_id == cliente.id
    )
    linhas = (
        await db.execute(
            select(Ticket.title, Ticket.status, Ticket.created_at)
            .join(ticket_equipments, ticket_equipments.c.ticket_id == Ticket.id)
            .join(User, User.id == Ticket.creator_id)
            .where(
                ticket_equipments.c.equipment_id.in_(equipamentos),
                Ticket.id != ticket.id,
                de_quem,
            )
            .order_by(Ticket.created_at.desc())
            .limit(3)
        )
    ).all()

    if not linhas:
        return "nenhum"
    return "; ".join(
        f"{titulo} ({status.value}, {_to_sp(criado).strftime('%m/%Y')})"
        for titulo, status, criado in linhas
    )


async def monta_conversa(db: AsyncSession, ticket: Ticket, ate_agora: str) -> str:
    """
    O que já foi dito, em ordem — incluindo a mensagem que acabou de chegar.

    A mensagem nova ainda não foi commitada quando isto roda (ela nasce no
    mesmo commit da resposta), então ela entra por parâmetro. Sem isso, o
    modelo responderia à penúltima frase do cliente.
    """
    mensagens = (
        (
            await db.execute(
                select(ChatMessage)
                .where(ChatMessage.ticket_id == ticket.id, ChatMessage.is_system.is_(False))
                .order_by(ChatMessage.created_at)
            )
        )
        .scalars()
        .all()
    )

    linhas = ["[CONVERSA]"]
    for m in mensagens:
        quem = "Helô" if m.is_ai else "Cliente"
        linhas.append(f"{quem}: {m.content}")
    linhas.append(f"Cliente: {ate_agora}")
    return "\n".join(linhas)


def monta_prompt(cadastro: str, base_tecnica: str, conversa: str) -> str:
    """Os três blocos, na ordem em que o prompt de sistema os descreve."""
    return f"{cadastro}\n\n[BASE TÉCNICA]\n{base_tecnica}\n\n{conversa}"
