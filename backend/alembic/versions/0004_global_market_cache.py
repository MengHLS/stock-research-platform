"""Persist cross-market quotes and daily bars for offline-tolerant reads.

The table is an operational read-through cache, not a research dataset. Rows
are refreshed from the reviewed public provider and may be served as a marked
stale snapshot when that provider is unavailable.
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_global_market_cache"
down_revision = "0003_invitation_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_global_quote_snapshot",
        sa.Column("instrument_key", sa.String(64), primary_key=True),
        sa.Column("price", sa.Numeric(24, 8), nullable=False),
        sa.Column("previous_close", sa.Numeric(24, 8)),
        sa.Column("open", sa.Numeric(24, 8)),
        sa.Column("high", sa.Numeric(24, 8)),
        sa.Column("low", sa.Numeric(24, 8)),
        sa.Column("change", sa.Numeric(24, 8)),
        sa.Column("change_pct", sa.Numeric(24, 8)),
        sa.Column("quote_time", sa.DateTime()),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "market_global_daily_bar",
        sa.Column("instrument_key", sa.String(64), primary_key=True),
        sa.Column("trading_day", sa.Date(), primary_key=True),
        sa.Column("open", sa.Numeric(24, 8), nullable=False),
        sa.Column("high", sa.Numeric(24, 8), nullable=False),
        sa.Column("low", sa.Numeric(24, 8), nullable=False),
        sa.Column("close", sa.Numeric(24, 8), nullable=False),
        sa.Column("change_pct", sa.Numeric(24, 8)),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_global_bar_day", "market_global_daily_bar", ["trading_day"])


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is disabled; use a reviewed forward migration.")
