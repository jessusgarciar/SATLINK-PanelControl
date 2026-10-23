"""Solicitudes de comandos, idempotencia y evidencia persistida."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("commands",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(128), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("mission_id", "client_request_id", name="uq_command_request"),
        sa.CheckConstraint("status IN ('pending','sent','received','executed','rejected','expired')", name="ck_command_status"))
    op.create_index("ix_command_mission_created", "commands", ["mission_id", "created_at", "id"])


def downgrade() -> None:
    op.drop_table("commands")
