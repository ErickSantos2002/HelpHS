"""add kb_article_products (produtos do artigo da base de conhecimento)

Revision ID: p6k7l8m9n0o1
Revises: o5j6k7l8m9n0
Create Date: 2026-08-05

Artigo sem nenhuma linha aqui vale para TODOS os produtos — por isso os
artigos que já existem não precisam de backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "p6k7l8m9n0o1"
down_revision: str | None = "o5j6k7l8m9n0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "kb_article_products",
        sa.Column(
            "article_id",
            UUID(as_uuid=True),
            sa.ForeignKey("kb_articles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_kb_article_products_product_id", "kb_article_products", ["product_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_kb_article_products_product_id", table_name="kb_article_products")
    op.drop_table("kb_article_products")
