"""Misiones, eventos recibidos y archivo de telemetría."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("missions",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("application_id", sa.String(128), nullable=False),
        sa.Column("dev_eui", sa.String(16), nullable=False),
        sa.Column("configuration", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("source", "application_id", "dev_eui", name="uq_mission_device"))
    op.create_table("received_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source", sa.String(128), nullable=False),
        sa.Column("mission_id", sa.String(128), sa.ForeignKey("missions.id")),
        sa.Column("dev_eui", sa.String(16)),
        sa.Column("deduplication_id", sa.String(36)),
        sa.Column("received_at", sa.DateTime(timezone=True)),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(512)),
        sa.Column("raw_payload", sa.LargeBinary(), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("source", "dev_eui", "deduplication_id", name="uq_received_event"),
        sa.CheckConstraint("status IN ('accepted','rejected')", name="ck_received_status"))
    op.create_table("telemetry",
        sa.Column("id", sa.String(36), sa.ForeignKey("received_events.id"), primary_key=True),
        sa.Column("mission_id", sa.String(128), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False))
    op.create_index("ix_telemetry_mission_time_id", "telemetry", ["mission_id", "received_at", "id"])


def downgrade() -> None:
    op.drop_table("telemetry")
    op.drop_table("received_events")
    op.drop_table("missions")
