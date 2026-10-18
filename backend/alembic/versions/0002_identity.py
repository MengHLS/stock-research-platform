"""Create identity tables: accounts, credentials, sessions and login audit.

Ported from the legacy project's ``users`` table, which delegated identity to an
OAuth provider. Self-hosted registration/login needs a local credential store and
revocable sessions, so this migration adds them explicitly.

No legacy rows are imported: the old database is a separate read-only source and
password material cannot be migrated from an OAuth-only schema.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_identity"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_account",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_signed_in_at", sa.DateTime()),
    )
    # Unique by construction: the application lower-cases before insert, so this
    # index is also the case-insensitive guard.
    op.create_index("ix_user_account_email", "user_account", ["email"], unique=True)

    op.create_table(
        "user_credential",
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("password_updated_at", sa.DateTime(), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime()),
    )

    op.create_table(
        "user_session",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
        sa.Column("user_agent", sa.String(200), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
    )
    op.create_index("ix_user_session_token", "user_session", ["token_hash"], unique=True)
    op.create_index("ix_user_session_user", "user_session", ["user_id", "expires_at"])

    op.create_table(
        "login_attempt",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_login_attempt_email", "login_attempt", ["email", "created_at"])


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is disabled; use a reviewed forward migration.")
