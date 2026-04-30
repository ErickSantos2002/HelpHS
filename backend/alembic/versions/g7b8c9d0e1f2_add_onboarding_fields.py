"""add onboarding fields to users and equipment

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "g7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("company_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("cnpj", sa.String(18), nullable=True))
    op.add_column("users", sa.Column("company_city", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("company_state", sa.String(2), nullable=True))
    op.add_column(
        "users",
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.add_column(
        "equipments",
        sa.Column("owner_id", sa.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("equipments", sa.Column("location", sa.String(255), nullable=True))
    op.create_foreign_key(
        "fk_equipments_owner_id_users",
        "equipments",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_equipments_owner_id", "equipments", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_equipments_owner_id", table_name="equipments")
    op.drop_constraint("fk_equipments_owner_id_users", "equipments", type_="foreignkey")
    op.drop_column("equipments", "location")
    op.drop_column("equipments", "owner_id")

    op.drop_column("users", "onboarding_completed")
    op.drop_column("users", "company_state")
    op.drop_column("users", "company_city")
    op.drop_column("users", "cnpj")
    op.drop_column("users", "company_name")
