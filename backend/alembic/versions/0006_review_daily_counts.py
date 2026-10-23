"""Persist derived daily limit-up/down counts for recent trading days."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime

revision = "0006_review_daily_counts"
down_revision = "0005_review_index_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_review_daily_counts",
        sa.Column("trading_day", sa.Date(), primary_key=True),
        sa.Column("limit_up_close_count", sa.Integer(), nullable=False),
        sa.Column("limit_down_close_count", sa.Integer(), nullable=False),
        sa.Column("raw_limit_up_close_count", sa.Integer(), nullable=False),
        sa.Column("raw_limit_down_close_count", sa.Integer(), nullable=False),
        sa.Column("rule_known_bar_count", sa.Integer(), nullable=False),
        sa.Column("st_observed_bar_count", sa.Integer(), nullable=False),
        sa.Column("ipo_window_bar_count", sa.Integer(), nullable=False),
        sa.Column("coverage_status", sa.String(32), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime().with_variant(MySQLDateTime(fsp=6), "mysql"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_review_daily_counts_day",
        "market_review_daily_counts",
        ["trading_day"],
    )


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is disabled; use a reviewed forward migration.")
