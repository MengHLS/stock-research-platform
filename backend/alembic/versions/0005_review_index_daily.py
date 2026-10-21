"""Persist review-only public index daily bars in the application database."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime

revision = "0005_review_index_daily"
down_revision = "0004_global_market_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_review_index_daily",
        sa.Column("symbol", sa.String(16), primary_key=True),
        sa.Column("trading_day", sa.Date(), primary_key=True),
        sa.Column("open", sa.Numeric(24, 8), nullable=False),
        sa.Column("high", sa.Numeric(24, 8), nullable=False),
        sa.Column("low", sa.Numeric(24, 8), nullable=False),
        sa.Column("close", sa.Numeric(24, 8), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime().with_variant(MySQLDateTime(fsp=6), "mysql"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_review_index_daily_day",
        "market_review_index_daily",
        ["trading_day"],
    )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is disabled; use a reviewed forward migration.")
