"""
O histórico de aceites da Política de Privacidade — gravar, revogar, cobrar.

Cobrar segue a Decisão 2 (27/10/2026): a Política vigente bloqueia o backend
para todos os papéis; os Termos continuam só na tela, e só para clientes.

Os routers chamam este módulo em vez de montar `LgpdConsent` à mão por um
motivo só: a revisão gravada precisa vir SEMPRE da configuração vigente, e a
`origem` precisa ser uma das três que o CHECK do banco aceita. Espalhado por
quatro endpoints, cada um seria um lugar para esquecer uma das duas coisas.

Desenho em `docs/superpowers/specs/2026-08-31-registro-da-revisao-aceita-design.md`.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.models.models import LgpdConsent, UserRole

# O titular marcou a caixa no cadastro público.
ORIGEM_AUTO_CADASTRO = "auto_cadastro"
# Alguém da equipe criou a conta e afirmou o consentimento pela pessoa. Fica
# separado porque NÃO é manifestação do titular — se pode valer como tal é
# pergunta jurídica, e o registro não pode decidi-la escondendo a diferença.
ORIGEM_CRIADO_POR_TERCEIRO = "criado_por_terceiro"
# O titular concedeu depois do cadastro — pelo perfil ou pela tela de re-aceite.
ORIGEM_ALTERACAO_PROPRIA = "alteracao_propria"


def registra_aceite(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    origem: str,
    ip: str | None,
    agora: datetime,
    settings: Settings | None = None,
) -> LgpdConsent:
    """Acrescenta um aceite com as revisões vigentes. Não faz commit."""
    s = settings or get_settings()
    aceite = LgpdConsent(
        id=uuid.uuid4(),
        user_id=user_id,
        revisao_politica=s.lgpd_revisao_politica,
        revisao_termos=s.lgpd_revisao_termos,
        origem=origem,
        concedido_em=agora,
        ip=ip,
    )
    db.add(aceite)
    return aceite


async def revoga_aceites(db: AsyncSession, *, user_id: uuid.UUID, agora: datetime) -> None:
    """Marca `revogado_em` em todo aceite ainda aberto. Não apaga nada.

    Um UPDATE só, e não "o último aceite": se por qualquer caminho houver dois
    abertos, revogar precisa fechar os dois — sobrar um aberto faria a pessoa
    continuar parecendo consentida.
    """
    await db.execute(
        update(LgpdConsent)
        .where(LgpdConsent.user_id == user_id, LgpdConsent.revogado_em.is_(None))
        .values(revogado_em=agora)
    )


async def ultimo_aceite_vigente(db: AsyncSession, user_id: uuid.UUID) -> LgpdConsent | None:
    """O aceite mais recente que não foi revogado, ou None."""
    resultado = await db.execute(
        select(LgpdConsent)
        .where(LgpdConsent.user_id == user_id, LgpdConsent.revogado_em.is_(None))
        .order_by(LgpdConsent.concedido_em.desc())
        .limit(1)
    )
    return resultado.scalars().first()


@dataclass(frozen=True)
class SituacaoDoAceite:
    """O que falta a pessoa aceitar, com a Política e os Termos SEPARADOS.

    Os dois campos têm usos diferentes, e é por isso que não são um booleano
    só:

    - `politica_pendente` BLOQUEIA o backend (`get_current_user` responde 428
      e o WebSocket fecha com 4428). Decisão 2, de 27/10/2026: aceite
      obrigatório da revisão vigente da Política, para todos os papéis.
    - `termos_pendentes` só informa a tela de re-aceite, e só de clientes —
      o comportamento de 24/09/2026, preservado. A Decisão 2 não autoriza
      bloquear a API por mudança apenas nos Termos; nenhum caminho do backend
      pode ler este campo para recusar um pedido.
    """

    politica_pendente: bool
    termos_pendentes: bool

    @property
    def precisa_reaceitar(self) -> bool:
        """O booleano antigo, só para apresentação.

        Mantido para o bundle do front anterior a esta mudança continuar
        funcionando durante o deploy. Não serve para decidir bloqueio.
        """
        return self.politica_pendente or self.termos_pendentes


# As origens que são manifestação do PRÓPRIO titular. `criado_por_terceiro`
# fica de fora de propósito (Decisão 2C): o registro da criação pela equipe
# continua existindo, mas não satisfaz o aceite da revisão vigente.
ORIGENS_PROPRIAS = frozenset({ORIGEM_AUTO_CADASTRO, ORIGEM_ALTERACAO_PROPRIA})


async def aceites_abertos(db: AsyncSession, user_id: uuid.UUID) -> list[LgpdConsent]:
    """Os aceites não revogados da pessoa, do mais recente para o mais antigo.

    Uma consulta só, pelo índice de `user_id`: é dela que saem a situação do
    aceite, a idempotência do PATCH e a resposta da tela.
    """
    resultado = await db.execute(
        select(LgpdConsent)
        .where(LgpdConsent.user_id == user_id, LgpdConsent.revogado_em.is_(None))
        .order_by(LgpdConsent.concedido_em.desc())
    )
    return list(resultado.scalars().all())


def avalia_aceite(
    abertos: Sequence[LgpdConsent], *, role: UserRole, settings: Settings
) -> SituacaoDoAceite:
    """A situação do aceite a partir dos aceites abertos (`aceites_abertos`).

    Com `LGPD_EXIGE_REACEITE` desligado nada fica pendente — é o estado de
    hoje em produção, e é o que faz este código entrar inerte.

    Política: pendente quando não existe NENHUMA linha aberta, de origem
    própria, com a revisão vigente. "Existe alguma", e não "a última": não
    depende da ordem das linhas, e várias abertas não atrapalham. Os Termos
    não entram aqui. Sem linha nenhuma, fica pendente — a revisão de quem se
    cadastrou antes do histórico é desconhecida, e `users.lgpd_consent` não
    prova revisão nenhuma.

    Termos: a regra de 24/09/2026, sem mudança — só clientes, e pendente
    quando não há aceite aberto ou o mais recente traz outra revisão dos
    Termos (inclusive os Termos passando a existir depois).
    """
    if not settings.lgpd_exige_reaceite:
        return SituacaoDoAceite(politica_pendente=False, termos_pendentes=False)

    politica_ok = any(
        a.origem in ORIGENS_PROPRIAS and a.revisao_politica == settings.lgpd_revisao_politica
        for a in abertos
    )
    ultimo = abertos[0] if abertos else None
    termos_pendentes = role == UserRole.client and (
        ultimo is None or ultimo.revisao_termos != settings.lgpd_revisao_termos
    )
    return SituacaoDoAceite(politica_pendente=not politica_ok, termos_pendentes=termos_pendentes)


async def situacao_do_aceite(
    db: AsyncSession, *, user_id: uuid.UUID, role: UserRole, settings: Settings
) -> SituacaoDoAceite:
    """`avalia_aceite` com a consulta. Com o interruptor desligado, nem consulta."""
    if not settings.lgpd_exige_reaceite:
        return SituacaoDoAceite(politica_pendente=False, termos_pendentes=False)
    return avalia_aceite(await aceites_abertos(db, user_id), role=role, settings=settings)


def ja_aceitou_as_revisoes_vigentes(abertos: Sequence[LgpdConsent], *, settings: Settings) -> bool:
    """Se aceitar agora repetiria um aceite próprio que já está aberto.

    É o que torna o PATCH idempotente: mesma revisão da Política E dos Termos
    (a comparação em Python trata `None == None` como igual, que é o que o
    `IS NOT DISTINCT FROM` faria no SQL), origem própria, não revogado.
    """
    return any(
        a.origem in ORIGENS_PROPRIAS
        and a.revisao_politica == settings.lgpd_revisao_politica
        and a.revisao_termos == settings.lgpd_revisao_termos
        for a in abertos
    )
