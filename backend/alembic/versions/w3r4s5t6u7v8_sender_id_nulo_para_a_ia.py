"""mensagem de chat aceita remetente nulo, para a Helo falar

Revision ID: w3r4s5t6u7v8
Revises: v2q3r4s5t6u7
Create Date: 2026-08-26

Primeiro tijolo da Helo Fase 1. `chat_messages.sender_id` era NOT NULL, e a
mensagem dela nao tem gente do outro lado.

A alternativa era criar um usuario "Helo" no banco. Ela apareceria na lista de
tecnicos, poderia ser atribuida a um chamado e receberia e-mail de
notificacao -- tres problemas novos para resolver um. O nulo com `is_ai = true`
segue o padrao que `ticket_history.user_id` ja usa para acao automatica do
sistema.

Sem risco no upgrade: afrouxar NOT NULL nunca falha, e nenhuma linha existente
muda. O `is_ai` ja existe desde a primeira migration -- e ate hoje nenhuma
linha do sistema jamais gravou `true` nele.

O DOWNGRADE pode falhar, e e a natureza da volta: se a Helo ja tiver falado,
existem linhas com `sender_id` nulo e o NOT NULL nao volta sem apagar a fala
dela. Quem precisar voltar decide o que fazer com essas linhas antes -- o
downgrade nao apaga mensagem de ninguem por conta propria.
"""

from collections.abc import Sequence

from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "w3r4s5t6u7v8"
down_revision: str | None = "v2q3r4s5t6u7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "chat_messages",
        "sender_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "chat_messages",
        "sender_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
