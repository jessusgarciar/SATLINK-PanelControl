"""Intentos, cadencia persistente y última predicción válida."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("prediction_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("mission_id", sa.String(128), sa.ForeignKey("missions.id"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_allowed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("raw_request", postgresql.JSONB(), nullable=False),
        sa.Column("raw_response", postgresql.JSONB()),
        sa.Column("normalized", postgresql.JSONB()),
        sa.Column("error", sa.String(128)),
        sa.CheckConstraint("status IN ('pending','succeeded','failed')", name="ck_prediction_status"))
    op.create_index("ix_prediction_mission_requested", "prediction_attempts", ["mission_id", "requested_at", "id"])


def downgrade() -> None:
    op.drop_table("prediction_attempts")
