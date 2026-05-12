"""add groups and companies

Revision ID: j0e1f2g3h4i5
Revises: i9d0e1f2g3h4
Create Date: 2026-05-12

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "j0e1f2g3h4i5"
down_revision: str | None = "i9d0e1f2g3h4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "groups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_groups_name", "groups", ["name"])

    op.create_table(
        "companies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "group_id",
            UUID(as_uuid=True),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("cnpj", sa.String(18), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("address", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(2), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_companies_group_id", "companies", ["group_id"])

    op.add_column(
        "users",
        sa.Column(
            "company_id",
            UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("users", sa.Column("client_notes", sa.Text, nullable=True))
    op.create_index("ix_users_company_id", "users", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_users_company_id", table_name="users")
    op.drop_column("users", "client_notes")
    op.drop_column("users", "company_id")
    op.drop_index("ix_companies_group_id", table_name="companies")
    op.drop_table("companies")
    op.drop_index("ix_groups_name", table_name="groups")
    op.drop_table("groups")
