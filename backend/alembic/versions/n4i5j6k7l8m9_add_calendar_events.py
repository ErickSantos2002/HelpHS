"""add calendar_events table

Revision ID: n4i5j6k7l8m9
Revises: m3h4i5j6k7l8
Create Date: 2026-06-08

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "n4i5j6k7l8m9"
down_revision: str | None = "m3h4i5j6k7l8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "event_type",
            sa.Enum("event", "meeting", "training", "deadline", "holiday", name="calendareventtype"),
            nullable=False,
            server_default="event",
        ),
        sa.Column("color", sa.String(7), nullable=False, server_default="#6366f1"),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_calendar_events_start_date", "calendar_events", ["start_date"])


def downgrade() -> None:
    op.drop_index("ix_calendar_events_start_date", table_name="calendar_events")
    op.drop_table("calendar_events")
    op.execute("DROP TYPE IF EXISTS calendareventtype")
