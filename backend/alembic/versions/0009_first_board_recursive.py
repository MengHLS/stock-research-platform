"""Store imported first-board recursive structure snapshots (two result layers)."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME as MySQLDateTime

revision = "0009_first_board_recursive"
down_revision = "0008_first_board_current"
branch_labels = None
depends_on = None

SNAPSHOT = "research_first_board_recursive_snapshot"
TARGET = "research_first_board_recursive_target"
CANDIDATE = "research_first_board_recursive_candidate"


def upgrade():
    op.create_table(
        SNAPSHOT,
        sa.Column("snapshot_id", sa.String(64), primary_key=True),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("board_scope", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("verification_status", sa.String(16), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False),
        sa.Column("first_board_count", sa.Integer(), nullable=False),
        sa.Column("candidate_link_count", sa.Integer(), nullable=False),
        sa.Column(
            "computed_at", sa.DateTime().with_variant(MySQLDateTime(fsp=6), "mysql"), nullable=False
        ),
    )
    op.create_index(
        "ix_first_board_recursive_snapshot_day",
        SNAPSHOT,
        ["trade_date", "board_scope"],
    )
    op.create_table(
        TARGET,
        sa.Column(
            "snapshot_id",
            sa.String(64),
            sa.ForeignKey(f"{SNAPSHOT}.snapshot_id"),
            primary_key=True,
        ),
        sa.Column("stock_code", sa.String(16), primary_key=True),
        sa.Column("target_order", sa.Integer(), nullable=False),
        sa.Column("stock_name", sa.String(32), nullable=False),
        sa.Column("theme", sa.String(32)),
        sa.Column("target_date", sa.Date(), nullable=False),
        *[sa.Column(name, sa.Numeric(30, 12)) for name in ("target_close", "limit_rate")],
        sa.Column("board_count", sa.Integer()),
        sa.Column("board_count_text", sa.String(24)),
        sa.Column("first_board_since_2019", sa.Integer()),
        sa.Column("prior_first_board_count", sa.Integer()),
        sa.Column("prior_eligible_non_st_count", sa.Integer()),
        sa.Column("nearest_prior_date", sa.Date()),
        sa.Column("nearest_stage", sa.String(48)),
        sa.Column("nearest_distance_sessions", sa.Integer()),
        sa.Column("anchor_date", sa.Date()),
        sa.Column("anchor_stage", sa.String(48)),
        sa.Column("anchor_reference_peak_date", sa.Date()),
        sa.Column("anchor_reference_peak", sa.Numeric(30, 12)),
        sa.Column("anchor_pullback_low_date", sa.Date()),
        sa.Column("anchor_pullback_low", sa.Numeric(30, 12)),
        sa.Column("anchor_pullback_pct", sa.Numeric(30, 12)),
        sa.Column("anchor_first_close_break_date", sa.Date()),
        sa.Column("anchor_target_close_vs_reference_pct", sa.Numeric(30, 12)),
        sa.Column("anchor_distance_sessions", sa.Integer()),
        sa.Column("selection_reason", sa.String(48), nullable=False),
        sa.Column("result_stage", sa.String(48), nullable=False),
        sa.Column("layers_diverge", sa.Boolean(), nullable=False),
        sa.Column("relation_status", sa.String(48)),
        sa.Column("diagnostic_codes", sa.String(512)),
        sa.Column("diagnostic_detail", sa.String(1024)),
        sa.Column("legacy_anchor_date", sa.Date()),
        sa.Column("legacy_anchor_stage", sa.String(48)),
        sa.Column("legacy_selection_reason", sa.String(48)),
        sa.Column("code_correction_from", sa.String(16)),
        sa.Column("code_correction_to", sa.String(16)),
    )
    op.create_index(
        "ix_first_board_recursive_target_stage",
        TARGET,
        ["snapshot_id", "result_stage"],
    )
    op.create_table(
        CANDIDATE,
        sa.Column(
            "snapshot_id",
            sa.String(64),
            sa.ForeignKey(f"{SNAPSHOT}.snapshot_id"),
            primary_key=True,
        ),
        sa.Column("stock_code", sa.String(16), primary_key=True),
        sa.Column("candidate_date", sa.Date(), primary_key=True),
        sa.Column("rank_oldest", sa.Integer(), nullable=False),
        sa.Column("rank_nearest", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(48), nullable=False),
        sa.Column("limit_rate", sa.Numeric(30, 12)),
        sa.Column("anchor_session_distance", sa.Integer()),
        sa.Column("reference_peak_date", sa.Date()),
        sa.Column("reference_peak", sa.Numeric(30, 12)),
        sa.Column("pullback_low_date", sa.Date()),
        sa.Column("pullback_low", sa.Numeric(30, 12)),
        sa.Column("pullback_pct", sa.Numeric(30, 12)),
        sa.Column("first_close_break_date", sa.Date()),
        sa.Column("target_close_vs_reference_pct", sa.Numeric(30, 12)),
        sa.Column("is_selected_anchor", sa.Boolean(), nullable=False),
        sa.Column("is_legacy_anchor", sa.Boolean(), nullable=False),
        sa.Column("selection_reason", sa.String(48)),
        sa.Column("legacy_selection_reason", sa.String(48)),
        sa.Column("relation_status", sa.String(48)),
        sa.Column("relation_price_reasons", sa.String(512)),
        sa.Column("relation_price_diagnostic", sa.String(1024)),
    )
    op.create_index(
        "ix_first_board_recursive_candidate_stock",
        CANDIDATE,
        ["stock_code", "candidate_date"],
    )


def downgrade():
    raise RuntimeError("Destructive downgrade is disabled; use a reviewed forward migration.")
