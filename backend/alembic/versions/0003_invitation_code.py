"""Create invitation codes for gated registration.

A code is the approval: whoever holds a valid one may register, so the operator
never has to flip an account state afterwards. Only the code's hash is stored, so
a database leak cannot produce working codes.
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_invitation_code"
down_revision = "0002_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invitation_code",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime()),
        sa.Column("used_at", sa.DateTime()),
        sa.Column(
            "used_by_user_id",
            sa.Integer(),
            sa.ForeignKey("user_account.id", ondelete="SET NULL"),
        ),
        sa.Column("revoked_at", sa.DateTime()),
    )
    op.create_index("ix_invitation_code_hash", "invitation_code", ["code_hash"], unique=True)
    op.create_index("ix_invitation_code_state", "invitation_code", ["used_at", "expires_at"])


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is disabled; use a reviewed forward migration.")
