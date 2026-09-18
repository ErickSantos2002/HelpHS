"""
Quem alcança um arquivo da biblioteca.

Dois consumidores, e a recusa é DIFERENTE em cada um de propósito:

- **o download** recusa com 404 para o cliente. Ele não pode aprender que o
  arquivo existe: 403 confirmaria a existência de um item interno para quem
  não deveria saber que ele está lá. É a mesma escolha que os anexos de chamado
  já fazem — anexo inexistente e anexo alheio dão a mesma resposta.

- **anexar no chat** recusa com 422 e explica. Ali quem age é o técnico, que
  precisa entender por que não pode mandar aquele arquivo; esconder a razão só
  faria ele tentar de novo.

Por que existe regra: manual não é material público por definição — há manual
técnico com senha de configuração em texto aberto. O default da coluna é
`internal`, então esquecer falha do lado seguro.
"""

from fastapi import HTTPException, status

from app.models.models import LibraryFile, LibraryVisibility, User, UserRole

_STAFF = (UserRole.admin, UserRole.technician)


def e_staff(actor: User) -> bool:
    return actor.role in _STAFF


def visivel_para_cliente(arquivo: LibraryFile) -> bool:
    """Só o que foi explicitamente aberto. Qualquer outro valor é fechado."""
    return arquivo.visibility is LibraryVisibility.client


def ensure_pode_baixar(arquivo: LibraryFile, actor: User, nao_encontrado: str) -> None:
    """Staff baixa qualquer um; cliente só o que está aberto para cliente.

    Sem esta conferência o link com validade viraria a rota de fuga da regra:
    o cliente não veria o item na listagem (que é só de staff), mas bastaria
    ter o id para baixar.
    """
    if e_staff(actor):
        return
    if not visivel_para_cliente(arquivo):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=nao_encontrado)


def ensure_pode_anexar_no_chat(arquivo: LibraryFile) -> None:
    """Item interno não entra em conversa, porque o cliente lê a conversa.

    A recusa é da API e vem ANTES de qualquer gravação. Deixar isso para a tela
    seria confiar a regra a quem não a executa: a API é chamada por outros
    clientes além dela, e uma tela desatualizada bastaria para vazar.
    """
    if not visivel_para_cliente(arquivo):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Este arquivo da biblioteca é de uso interno e não pode ser anexado "
                "a uma conversa, que o cliente lê. Um administrador precisa abri-lo "
                "para cliente antes."
            ),
        )
