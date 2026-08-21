"""
Recusa de chamado alheio — ponto único.

A regra estava copiada em quatro arquivos sob três nomes (`_check_ticket_access`
em anexos, `_get_ticket_or_403` no chat, e inline em tickets e avaliações), e
respondia `403`. O `403` diz "existe, mas não é seu": para quem só tem o id,
isso é meia resposta a mais do que deveria conseguir. Mesmo formato que os
equipamentos ganharam no `637ad0f`.
"""

from fastapi import HTTPException, status

from app.models.models import Ticket, User


def ensure_ticket_visible(ticket: Ticket, actor: User, not_found_detail: str) -> None:
    """
    Recusa o chamado que não foi aberto pelo ator, como se ele não existisse.

    **Este helper não abre exceção para staff — quem decide isso é o call
    site.** É deliberado, e foi a decisão que evitou ampliar permissão sem
    querer no `_check_equipment_owner` (`2ad773c`): um helper que "sabe" que
    admin passa vira um passe-livre invisível no dia em que alguém o chamar de
    um endpoint novo sem ler o corpo dele. Aqui a regra é só "é seu?", e cada
    endpoint diz em voz alta quem ele submete a ela — hoje, sempre e apenas o
    perfil `client`.

    `not_found_detail` é obrigatório e deve ser **o mesmo texto** que o
    endpoint passa ao `get_or_404` do recurso pedido. Sem isso a recusa vira um
    404 de mensagem diferente, que continua separando "não é seu" de "não
    existe" — só que com mais disfarce. Há teste de paridade guardando isso em
    cada arquivo.

    Args:
        ticket: Chamado já carregado do banco.
        actor: Usuário autenticado da requisição.
        not_found_detail: Texto idêntico ao 404 de id inexistente do endpoint.

    Raises:
        HTTPException: 404 se o ator não for o autor do chamado.
    """
    if ticket.creator_id != actor.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=not_found_detail,
        )
