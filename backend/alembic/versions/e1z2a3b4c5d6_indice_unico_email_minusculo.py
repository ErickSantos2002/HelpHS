"""índice único em lower(email): identidade sem distinção de maiúsculas

Revision ID: e1z2a3b4c5d6
Revises: d0y1z2a3b4c5
Create Date: 2026-09-15

`Fulano@x.com` e `fulano@x.com` são a mesma caixa postal no mundo real, mas o
índice único ingênuo em `email` os aceitava como duas contas. A regra
prospectiva vive no tipo (`EmailNormalizado`, que baixa toda entrada); este
índice é a trava de banco — segura o endpoint futuro que esquecer o tipo e a
corrida de dois cadastros simultâneos com caixas diferentes.

ATENÇÃO: roda sozinha no boot. Se o banco tiver duplicata por caixa, a criação
FALHA e a API não sobe — de propósito: subir com a duplicata seria pior. O
passado é do `scripts/normaliza_emails.py`, que deve rodar ANTES do deploy
(produção foi conferida limpa em 15/09).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e1z2a3b4c5d6"
down_revision: str | None = "d0y1z2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_lower", table_name="users")
