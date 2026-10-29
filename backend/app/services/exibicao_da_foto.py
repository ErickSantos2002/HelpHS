"""
A autorização para a foto de perfil aparecer para outras pessoas (Fase 3B).

Três coisas moram aqui, e só aqui:

1. **O texto, junto da versão.** A tela recebe o texto do servidor em vez de
   tê-lo no bundle. É isso que faz a versão gravada no registro identificar o
   que a pessoa leu: o navegador devolve a versão que mostrou, o servidor
   confere com a vigente e grava a DELE. Uma versão inventada pelo navegador
   nunca chega ao banco.
2. **Qual versão vale**, que vem de `AVATAR_AVISO_EXIBICAO_VERSAO`. Ela
   controla SÓ se dá para autorizar agora. Vazia, desconhecida ou apontando
   para um texto não aprovado em produção, ninguém autoriza — mas quem já
   autorizou continua autorizado: esta variável NÃO é um interruptor da
   exibição, que olha apenas a escolha gravada (`app/utils/avatar.py`).
3. **A troca do estado com o evento**, sempre juntos e na mesma transação.

O que NÃO mora aqui é a regra de quem vê a foto de quem: isso continua em
`app/utils/avatar.py`. A autorização é uma condição a MAIS sobre aquela
matriz; ela não abre nada que a matriz fecha.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.models import AvatarVisibilityEvent, User, UserRole

EVENTO_AUTORIZACAO = "autorizacao"
EVENTO_REVOGACAO = "revogacao"
# Só o titular muda a própria escolha. Mesmo nome da origem equivalente em
# `lgpd_consents`; não existe origem "criado por terceiro" aqui, porque
# ninguém autoriza pela pessoa.
ORIGEM_ALTERACAO_PROPRIA = "alteracao_propria"


@dataclass(frozen=True)
class Aviso:
    """O texto que a pessoa lê antes de decidir, numa versão."""

    versao: str
    rotulo: str
    # Só um texto marcado aqui como aprovado vale em PRODUÇÃO. É a marca
    # explícita, e não o nome: "não começa com MINUTA" não prova aprovação, e
    # configurar a versão no painel não transforma um rascunho em texto
    # aprovado. Fora de produção qualquer texto do catálogo serve, para que
    # desenvolvimento e testes exercitem o fluxo inteiro.
    aprovado: bool
    # Por papel, porque quem vê a foto muda com ele: a explicação descreve a
    # matriz real (`app/utils/avatar.py`) e não promete exibição a quem não tem
    # acesso ao chamado.
    explicacao_cliente: tuple[str, ...]
    explicacao_equipe: tuple[str, ...]

    def explicacao_para(self, papel: UserRole) -> tuple[str, ...]:
        if papel in (UserRole.admin, UserRole.technician):
            return self.explicacao_equipe
        return self.explicacao_cliente


_COMUM = (
    "É opcional. Sem permissão, as outras pessoas veem as suas iniciais, e você "
    "continua abrindo chamados e conversando normalmente.",
    "A permissão vale para a foto que estiver no seu perfil a cada momento: se "
    "você trocar a foto, a nova aparece no lugar; se remover, aparecem as iniciais.",
    "Você pode desligar quando quiser. A partir daí, as telas abertas depois "
    "mostram as suas iniciais. Uma tela que outra pessoa já tinha aberto pode "
    "continuar mostrando a foto por algum tempo, e uma imagem que já foi "
    "carregada ou copiada não some por causa disso.",
    "Desligar não apaga a sua foto: ela continua no seu perfil, para você.",
)

# ⚠️ MINUTA. O texto final depende do responsável pela Política, e a versão
# aprovada entra aqui com OUTRO nome — nunca editando esta no lugar, porque o
# nome é o que os registros já gravados apontam. O prefixo fica gravado em cada
# evento, então uma autorização registrada contra a minuta diz que foi isso.
AVISOS: dict[str, Aviso] = {
    "MINUTA-2026-10-21": Aviso(
        versao="MINUTA-2026-10-21",
        aprovado=False,
        rotulo=(
            "Permitir que minha foto apareça para outros participantes dos "
            "atendimentos, nos chamados em que essa visualização é permitida."
        ),
        explicacao_cliente=(
            "Se você permitir, a equipe de atendimento (técnicos e administradores) "
            "verá a sua foto nos chamados que você abriu e nas mensagens que você "
            "enviar neles. Outros clientes nunca veem a sua foto.",
            *_COMUM,
        ),
        explicacao_equipe=(
            "Se você permitir, a sua foto aparece para a equipe nos chamados, para "
            "o cliente nos chamados em que você é o responsável e, nas conversas, "
            "junto das mensagens que você enviar — para a equipe e para o cliente "
            "que abriu o chamado.",
            *_COMUM,
        ),
    ),
}


def aviso_vigente(settings: Settings) -> Aviso | None:
    """O aviso que vale agora, ou None se não dá para autorizar agora.

    Versão configurada sem texto correspondente também é None: melhor a opção
    indisponível do que gravar uma versão que não aponta para texto nenhum. E,
    em produção, texto não aprovado também: uma autorização real nunca é
    registrada contra minuta ou texto de teste.
    """
    versao = settings.avatar_aviso_exibicao_versao
    if versao is None:
        return None
    aviso = AVISOS.get(versao)
    if aviso is None:
        return None
    if settings.is_production and not aviso.aprovado:
        return None
    return aviso


class AvisoDesatualizadoError(Exception):
    """A tela mostrou outro texto (ou nenhum) que não o vigente."""


class AutorizacaoIndisponivelError(Exception):
    """Não há texto vigente: ninguém consegue autorizar agora."""


def altera_exibicao(
    db: AsyncSession,
    *,
    usuario: User,
    autorizada: bool,
    versao_apresentada: str | None,
    ip: str | None,
    agora: datetime,
    settings: Settings,
) -> AvatarVisibilityEvent | None:
    """Aplica a escolha do titular. Não faz commit, e não trava a linha.

    Quem chama precisa ter travado `usuario` (`FOR UPDATE`) na mesma transação
    e fazer o commit depois: é isso que deixa estado e evento indo juntos, e
    que faz dois pedidos simultâneos se enfileirarem em vez de gravarem dois
    eventos iguais.

    Devolve o evento acrescentado, ou None quando a escolha já era a atual —
    repetir não gera registro.

    - Autorizar exige o texto vigente E a confirmação de que foi ele o
      apresentado. A versão gravada é a do servidor.
    - Revogar não depende do texto: funciona com a opção indisponível, sem
      aceite novo. A versão vai no registro só se a tela confirmou a vigente;
      senão fica nula, em vez de afirmar um texto que talvez não tenha sido
      mostrado. (Chegar até aqui exige conta ATIVA: o `get_current_user`
      recusa as outras antes — ver `foto_visivel_*` para o que acontece com a
      foto delas.)
    """
    vigente = aviso_vigente(settings)
    if autorizada:
        if vigente is None:
            raise AutorizacaoIndisponivelError
        if versao_apresentada != vigente.versao:
            raise AvisoDesatualizadoError

    if usuario.avatar_visivel_a_terceiros is autorizada:
        return None

    versao = vigente.versao if vigente and versao_apresentada == vigente.versao else None
    evento = AvatarVisibilityEvent(
        id=uuid.uuid4(),
        user_id=usuario.id,
        evento=EVENTO_AUTORIZACAO if autorizada else EVENTO_REVOGACAO,
        versao_aviso=versao,
        origem=ORIGEM_ALTERACAO_PROPRIA,
        registrado_em=agora,
        ip=ip,
    )
    usuario.avatar_visivel_a_terceiros = autorizada
    # `updated_at` fica como estava, de propósito e no próprio UPDATE: sem
    # isto, o `onupdate` do model o renovaria. Ele é o token de versão da
    # remoção da foto pelo admin, e mudar a preferência faria aquela tela
    # acusar "pode ser uma foto nova" sem foto nova nenhuma. É o valor da
    # PRÓPRIA linha travada, lido pelo banco no UPDATE — não um horário
    # guardado antes da trava. O momento da escolha mora no evento.
    usuario.updated_at = User.updated_at
    db.add(evento)
    return evento


def encerra_por_anonimizacao(usuario: User) -> bool:
    """A anonimização encerra a autorização. Não faz commit, e não trava a linha.

    Quem chama precisa ter travado `usuario` (`FOR UPDATE`) na mesma transação
    da anonimização: sem a trava, um `PUT` do titular que comitasse entre a
    leitura e o UPDATE deixaria `True` gravado numa conta anonimizada (o ORM
    só manda a coluna que viu mudar).

    NÃO é revogação, e por isso NÃO grava `AvatarVisibilityEvent`: aquele
    registro é a manifestação do titular, e quem anonimiza é outra pessoa.
    Quem chama registra o efeito no AuditLog da própria anonimização, com o
    ator verdadeiro. Os eventos antigos ficam como estão.

    Diferente da conta só inativa — que guarda a escolha e volta a respeitá-la
    ao reativar —, a anonimizada perde a autorização de vez. A conta
    anonimizada não volta pelo `PATCH /status` (é terminal ali); se um dia
    houver fluxo próprio de recuperação, a foto só aparece com nova autorização.

    Devolve se havia autorização.
    """
    havia = usuario.avatar_visivel_a_terceiros
    usuario.avatar_visivel_a_terceiros = False
    return havia
