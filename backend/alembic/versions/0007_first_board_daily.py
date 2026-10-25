"""Store versioned first-board background observations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime

revision = "0007_first_board_daily"
down_revision = "0006_review_daily_counts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_first_board_daily_batch",
        sa.Column("batch_id", sa.String(64), primary_key=True),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("dataset_version_id", sa.String(32), nullable=False),
        sa.Column("source_version", sa.String(64), nullable=False),
        sa.Column("universe_definition", sa.Text(), nullable=False),
        sa.Column("taxonomy_version", sa.String(48), nullable=False),
        sa.Column("feature_version", sa.String(48), nullable=False),
        sa.Column("source_event_count", sa.Integer(), nullable=False),
        sa.Column(
            "computed_at", sa.DateTime().with_variant(MySQLDateTime(fsp=6), "mysql"), nullable=False
        ),
    )
    op.create_index(
        "ix_first_board_batch_day",
        "research_first_board_daily_batch",
        ["trading_day", "computed_at"],
    )
    op.create_table(
        "research_first_board_background_event",
        sa.Column(
            "batch_id",
            sa.String(64),
            sa.ForeignKey("research_first_board_daily_batch.batch_id"),
            primary_key=True,
        ),
        sa.Column("event_id", sa.String(64), primary_key=True),
        sa.Column("trading_day", sa.Date(), nullable=False),
        sa.Column("stock_code", sa.String(16), nullable=False),
        sa.Column("feature_cutoff", sa.Date()),
        sa.Column("class_code", sa.String(16)),
        sa.Column("group_code", sa.String(16)),
        sa.Column("position_band", sa.String(16), nullable=False),
        sa.Column("trend", sa.String(16), nullable=False),
        sa.Column("short_path", sa.String(24), nullable=False),
        *[
            sa.Column(name, sa.Numeric(30, 12))
            for name in (
                "position_60d_pct",
                "return_5d_pct",
                "return_20d_pct",
                "return_60d_pct",
                "ma_20",
                "ma_60",
            )
        ],
        sa.Column("quality_status", sa.String(16), nullable=False),
        sa.Column("feature_reason", sa.String(512)),
    )
    op.create_index(
        "ix_first_board_event_stock",
        "research_first_board_background_event",
        ["stock_code", "trading_day"],
    )


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; use a reviewed forward migration.")
