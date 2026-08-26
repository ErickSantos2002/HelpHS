"""segundo fator (TOTP) para o staff

Revision ID: v2q3r4s5t6u7
Revises: u1p2q3r4s5t6
Create Date: 2026-08-26

Três colunas em `users` e uma restrição que impede o único estado quebrado.

`mfa_secret` guarda o segredo TOTP **cifrado**, não hasheado. A distinção não é
estilo: conferir um código exige recalculá-lo a partir do segredo a cada
tentativa, então o servidor precisa recuperá-lo em claro — um hash tornaria a
verificação impossível. O que protege a coluna é a chave da cifra morar fora do
banco, em `MFA_SECRET_ENCRYPTION_KEY`. Um dump desta tabela, sozinho, não gera
código nenhum.

A coluna tem 255 caracteres porque guarda o texto Fernet (base64 com IV e
timestamp), não os 32 do segredo base32 cru.

O CHECK recusa `mfa_enabled = true` sem segredo. Esse par é uma conta trancada:
o login exigiria um código que não há como conferir, e a pessoa não entraria
nem com a senha certa. A regra poderia viver só no código, e viveria bem até o
dia em que um caminho de escrita novo esquecesse dela — no banco, ela não tem
como ser esquecida.

SEM BACKFILL, e não é omissão. Toda linha existente nasce com `mfa_enabled`
falso porque é isso que é verdade: ninguém tem segundo fator ainda. Isso é
default de coluna, não reescrita de passado.

O UPGRADE é aditivo e não tranca ninguém: quem loga hoje continua logando
exatamente igual, porque `mfa_enabled` falso não muda caminho nenhum.

O DOWNGRADE apaga os segredos junto com as colunas. Quem já tiver aderido
precisa cadastrar de novo ao subir outra vez — não há como preservar, já que a
coluna some. Fazer backup antes de voltar, se houver alguém com MFA ativo.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "v2q3r4s5t6u7"
down_revision: str | None = "u1p2q3r4s5t6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("mfa_secret", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("mfa_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(
        "ck_users_mfa_ligado_tem_segredo",
        "users",
        "mfa_enabled = false OR mfa_secret IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_mfa_ligado_tem_segredo", "users", type_="check")
    op.drop_column("users", "mfa_confirmed_at")
    op.drop_column("users", "mfa_secret")
    op.drop_column("users", "mfa_enabled")
