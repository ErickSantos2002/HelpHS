"""
O histórico de aceites da Política de Privacidade — gravar, revogar, cobrar.

Os routers chamam este módulo em vez de montar `LgpdConsent` à mão por um
motivo só: a revisão gravada precisa vir SEMPRE da configuração vigente, e a
`origem` precisa ser uma das três que o CHECK do banco aceita. Espalhado por
quatro endpoints, cada um seria um lugar para esquecer uma das duas coisas.

Desenho em `docs/superpowers/specs/2026-08-31-registro-da-revisao-aceita-design.md`.
"""

import uuid
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


def precisa_reaceitar(ultimo: LgpdConsent | None, *, role: UserRole, settings: Settings) -> bool:
    """Se a pessoa precisa passar pela tela de aceite antes de usar o sistema.

    Decisões de 24/09/2026: só clientes, e só com `LGPD_EXIGE_REACEITE` ligado.
    Sem aceite registrado, precisa — a revisão de quem se cadastrou antes do
    histórico é desconhecida, e é esse vazio que cobra o aceite, em vez de
    fingir que foi a 00. Com aceite, precisa quando qualquer das duas revisões
    difere da vigente, inclusive os Termos passando a existir depois.
    """
    if not settings.lgpd_exige_reaceite or role != UserRole.client:
        return False
    if ultimo is None:
        return True
    return (
        ultimo.revisao_politica != settings.lgpd_revisao_politica
        or ultimo.revisao_termos != settings.lgpd_revisao_termos
    )
