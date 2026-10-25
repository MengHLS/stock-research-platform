"""Select a current immutable first-board batch, including reverted inputs."""

import sqlalchemy as sa
from alembic import op

revision = "0008_first_board_current"
down_revision = "0007_first_board_daily"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_first_board_daily_current",
        sa.Column("trading_day", sa.Date(), primary_key=True),
        sa.Column("taxonomy_version", sa.String(48), primary_key=True),
        sa.Column("feature_version", sa.String(48), primary_key=True),
        sa.Column(
            "batch_id",
            sa.String(64),
            sa.ForeignKey("research_first_board_daily_batch.batch_id"),
            nullable=False,
        ),
    )
    # Preserve the previous selection for any snapshots already present at 0007.
    op.execute(
        sa.text("""
        INSERT INTO research_first_board_daily_current
            (trading_day, taxonomy_version, feature_version, batch_id)
        SELECT b.trading_day, b.taxonomy_version, b.feature_version, b.batch_id
        FROM research_first_board_daily_batch b
        WHERE NOT EXISTS (
            SELECT 1 FROM research_first_board_daily_batch newer
            WHERE newer.trading_day = b.trading_day
              AND newer.taxonomy_version = b.taxonomy_version
              AND newer.feature_version = b.feature_version
              AND (newer.computed_at > b.computed_at
                   OR (newer.computed_at = b.computed_at AND newer.batch_id > b.batch_id))
        )
    """)
    )


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; use a reviewed forward migration.")
