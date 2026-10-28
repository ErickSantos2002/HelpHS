"""exibicao da foto de perfil a terceiros

Revision ID: l8g9h0i1j2k3
Revises: 0a17fd87823c
Create Date: 2026-10-21

A Fase 3B mostra a foto de perfil aos outros participantes de um chamado. Isso
passa a depender de uma autorização específica do titular, separada do aceite
da Política. Esta revision cria as duas peças:

- `users.avatar_visivel_a_terceiros`: o estado atual, NOT NULL, padrão falso
  no próprio banco;
- `avatar_visibility_events`: cada autorização e cada revogação, com a versão
  do texto apresentado, a origem, o momento (do servidor) e o IP.

TODO MUNDO COMEÇA SEM AUTORIZAÇÃO, E ISSO É O CERTO
----------------------------------------------------
Não há backfill. Quem enviou foto antes desta revision enviou quando ela só
aparecia para a própria pessoa, e aceitar a Política não é escolher mostrar a
foto. Converter upload ou `lgpd_consent` em autorização seria fabricar prova.
O `server_default` preenche as linhas existentes com falso, e a tabela de
eventos nasce vazia.

Nenhuma foto é apagada: `avatar_url` não é tocado. Protocolos, e-mails e
chamados também não.

`user_id` é `ON DELETE SET NULL`, como em `lgpd_consents`: excluir a conta não
apaga o registro de que houve a escolha, e o DELETE de usuário continua sem
bloqueio novo.

O DOWNGRADE derruba a tabela e a coluna: perde as escolhas gravadas desde a
subida, que só existem aqui. Descer em produção depois de escolhas reais exige
salvar a tabela antes.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "l8g9h0i1j2k3"
down_revision: str | None = "0a17fd87823c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# As mesmas regras dos `CheckConstraint` do model. O autogenerate não compara
# CHECK, então a paridade é conferida em `test_exibicao_da_foto_postgres.py`.
_REGRA_EVENTO = "evento IN ('autorizacao', 'revogacao')"
_REGRA_ORIGEM = "origem IN ('alteracao_propria')"
_REGRA_AVISO = "evento = 'revogacao' OR versao_aviso IS NOT NULL"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "avatar_visivel_a_terceiros",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_table(
        "avatar_visibility_events",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("evento", sa.String(20), nullable=False),
        sa.Column("versao_aviso", sa.String(40), nullable=True),
        sa.Column("origem", sa.String(30), nullable=False),
        sa.Column(
            "registrado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.CheckConstraint(_REGRA_EVENTO, name="ck_avatar_visibility_events_evento_conhecido"),
        sa.CheckConstraint(_REGRA_ORIGEM, name="ck_avatar_visibility_events_origem_conhecida"),
        sa.CheckConstraint(_REGRA_AVISO, name="ck_avatar_visibility_events_autorizacao_tem_aviso"),
    )
    op.create_index("ix_avatar_visibility_events_user_id", "avatar_visibility_events", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_avatar_visibility_events_user_id", table_name="avatar_visibility_events")
    op.drop_table("avatar_visibility_events")
    op.drop_column("users", "avatar_visivel_a_terceiros")
