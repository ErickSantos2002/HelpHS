"""
Foto de perfil: qual chave é legítima, quem pode vê-la e o link para vê-la.

Morava inteira em `routers/users.py`, que só servia a PRÓPRIA foto. A Fase 3B
mostra a foto dos participantes de um chamado — o técnico para o cliente, o
cliente para a equipe —, e o chamado e o chat não podem importar um router do
outro para isso. A regra veio para cá sem mudar uma linha do comportamento: o
router de usuários passa a importá-la com os nomes antigos.

O que este módulo NÃO faz é decidir se o ator enxerga o CHAMADO. Isso continua
nos call sites (`ensure_ticket_visible` e a sala do WebSocket). Aqui só se
decide, dentro de um chamado que o ator já pode ver, de quem ele pode ver a
foto — e, para a foto de outra pessoa, isso inclui ela estar ATIVA e ter
autorizado (`users.avatar_visivel_a_terceiros`, ver
`app/services/exibicao_da_foto.py`).
A conferência vem antes de `links_das_fotos`: sem ela, nada é assinado, e o
cache de assinatura nunca é consultado para quem não autorizou.
"""

import uuid
from collections.abc import Iterable

from loguru import logger

from app.core.config import Settings
from app.models.models import ChatMessage, Ticket, User, UserRole, UserStatus
from app.services import storage

# Tipo aceito no upload → extensão gravada. É daqui que sai o único formato de
# chave que um avatar já teve (`avatars/{id}{ext}`, desde `de2aa09`): o upload
# grava com ele, e a leitura só aceita de volta exatamente isso.
EXTENSOES_DO_AVATAR = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

_EQUIPE = (UserRole.admin, UserRole.technician)


def chave_do_avatar(user_id: uuid.UUID, extensao: str) -> str:
    return f"avatars/{user_id}{extensao}"


def chave_legitima_do_avatar(user: User) -> str | None:
    """A chave gravada, se for a que o upload produz para ESTE usuário.

    Até 09/10/2026 `avatar_url` era gravável por `PATCH /users/me` e
    `PATCH /users/{id}` com qualquer texto — URL externa, chave da foto de
    outra conta, caminho com `..`. O campo saiu do `UserUpdate`, mas o que
    foi gravado antes continua no banco, e não é corrigido em massa aqui.

    Por isso a leitura não confia no valor: compara por IGUALDADE com as
    quatro chaves que o upload poderia ter gerado para este id. Sem prefixo e
    sem parsing, não há travessia, maiúscula ou domínio de terceiro que passe.
    Qualquer outra coisa vira "sem foto", e o front cai nas iniciais.
    """
    chave = user.avatar_url
    if not chave:
        return None
    validas = {chave_do_avatar(user.id, ext) for ext in EXTENSOES_DO_AVATAR.values()}
    return chave if chave in validas else None


# ── Quem vê a foto de quem, dentro de um chamado visível ──────


def exibicao_autorizada(pessoa: User) -> bool:
    """O titular autorizou a própria foto a aparecer para outras pessoas?

    `is True`, e não verdade solta: qualquer coisa que não seja o booleano
    gravado — atributo ausente, nulo, um dublê de teste que responde a tudo —
    vale como "não autorizou". O erro, se houver, cai para o lado das iniciais.
    """
    return getattr(pessoa, "avatar_visivel_a_terceiros", False) is True


def titular_ativo(pessoa: User) -> bool:
    """A conta do dono da foto está ativa?

    Conta inativa ou anonimizada não emite foto para terceiros, com ou sem
    autorização gravada. Não é uma revogação: a escolha fica como a pessoa a
    deixou, nenhum evento é registrado em nome dela, e reativar a conta volta
    a respeitar o que estava gravado. É só a exibição que fica suspensa
    enquanto a conta não está ativa — inclusive porque, sem login, a pessoa
    não alcança a rota para revogar.

    Mesmo cuidado de `exibicao_autorizada`: só o status ativo de verdade vale;
    ausente ou desconhecido cai para as iniciais.
    """
    return getattr(pessoa, "status", None) == UserStatus.active


def pode_aparecer_para_terceiros(pessoa: User) -> bool:
    """As duas condições do titular, antes da matriz: ativo E autorizou."""
    return titular_ativo(pessoa) and exibicao_autorizada(pessoa)


def foto_visivel_no_chamado(pessoa: User, ator: User) -> bool:
    """O ator, que JÁ pode ver o chamado, pode ver a foto desta pessoa?

    - A própria foto o ator vê sempre: não há terceiro nenhum aqui.
    - A foto de outra pessoa só sai se a conta DELA está ativa e ela
      autorizou. São condições a mais, e não abrem o que a matriz abaixo fecha.
    - Equipe (técnico e admin) vê a foto de quem aparece no chamado: é a mesma
      equipe que já lê o sistema inteiro.
    - O cliente vê a de quem é da equipe — o técnico que o atende. Foto de
      OUTRO cliente não sai por aqui, mesmo que um dia ele apareça num chamado
      alheio por troca de papel ou dado antigo, e mesmo que tenha autorizado.
    """
    if pessoa.id == ator.id:
        return True
    if not pode_aparecer_para_terceiros(pessoa):
        return False
    if ator.role in _EQUIPE:
        return True
    return pessoa.role in _EQUIPE


def foto_visivel_na_conversa(remetente: User, ticket: Ticket) -> bool:
    """A foto deste remetente pode ir no payload da conversa deste chamado?

    ⚠️ Não depende de QUEM recebe, e é isso que permite um payload só. O
    WebSocket entrega a mesma mensagem a todos da sala — e, pelo backplane, a
    todos os processos —, e na sala entram a equipe e o CRIADOR do chamado. A
    regra é a do pior destinatário possível, o criador quando ele é cliente:
    ele pode ver a equipe e a si mesmo. Como a equipe vê tudo isso também, o
    mesmo payload serve aos dois lados, e o REST usa exatamente a mesma regra
    para que recarregar a tela não mostre nada diferente do tempo real.

    Pelo mesmo motivo, sem a autorização do remetente — ou com a conta dele
    não ativa — a mensagem sai sem foto para TODOS, ele incluído: o payload
    que chega a ele é o que chega à sala, e a sala tem terceiros. A própria
    foto ele continua vendo no perfil e no topo da tela, que não passam por
    aqui.
    """
    if not pode_aparecer_para_terceiros(remetente):
        return False
    return remetente.role in _EQUIPE or remetente.id == ticket.creator_id


def remetentes_com_foto(mensagens: Iterable[ChatMessage], ticket: Ticket) -> list[User]:
    """Os remetentes de pessoas cuja foto pode ir nesta conversa.

    Helô (`is_ai`) e aviso do sistema (`is_system`) ficam de fora: têm
    identidade visual própria na tela, e não são uma pessoa entre outras.
    """
    pessoas: list[User] = []
    for msg in mensagens:
        if msg.is_ai or msg.is_system:
            continue
        remetente = msg.sender
        if remetente is not None and foto_visivel_na_conversa(remetente, ticket):
            pessoas.append(remetente)
    return pessoas


# ── O link ────────────────────────────────────────────────────


async def links_das_fotos(pessoas: Iterable[User], settings: Settings) -> dict[uuid.UUID, str]:
    """Um link por PESSOA, não por aparição — e só para quem tem foto legítima.

    Cinquenta mensagens de três pessoas assinam três vezes. Quem não está no
    dicionário não tem foto para mostrar, e o call site usa `.get(id)`, que dá
    `None`: sem foto, foto apagada, referência indevida ou falha ao assinar
    caem todos no mesmo lugar — as iniciais.

    TTL dos ARQUIVOS (`file_url_expires_seconds`), e não os 7 dias da própria
    foto: esta é a foto de outra pessoa, que pode ser trocada ou removida, e o
    link dela não deve sobreviver ao dia. A janela e o cache da Fase 3.0 vêm
    de graça, porque a emissão é a mesma de qualquer arquivo.

    Falha ao assinar não derruba a resposta: o chamado abre e a mensagem é lida
    sem a foto. O log não leva a chave nem o link.
    """
    links: dict[uuid.UUID, str] = {}
    vistos: set[uuid.UUID] = set()
    for pessoa in pessoas:
        if pessoa.id in vistos:
            continue
        vistos.add(pessoa.id)
        chave = chave_legitima_do_avatar(pessoa)
        if chave is None:
            continue
        try:
            links[pessoa.id] = await storage.get_presigned_url(
                chave, settings, expires=settings.file_url_expires_seconds
            )
        except Exception as exc:  # noqa: BLE001 — a foto é acessória, o chamado não
            logger.warning(
                "Foto de perfil sem link para o usuário {}: {}", pessoa.id, type(exc).__name__
            )
    return links
