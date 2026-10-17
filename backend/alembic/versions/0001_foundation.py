"""Create starter catalog and platform diagnostic queue; no legacy data migration."""

import sqlalchemy as sa
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_entry",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
    )
    op.create_index("ix_catalog_owner_id", "catalog_entry", ["owner_user_id", "id"])
    op.create_table(
        "execution_job",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(60), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_until", sa.DateTime()),
        sa.Column("result", sa.JSON()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_user_id", "idempotency_key", name="uq_job_owner_key"),
    )
    op.create_index("ix_job_queue", "execution_job", ["state", "created_at"])
    op.create_index("ix_job_owner", "execution_job", ["owner_user_id", "id"])


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is disabled; use a reviewed forward migration.")
