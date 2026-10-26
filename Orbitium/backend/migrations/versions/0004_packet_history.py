"""Index the per-mission packet archive without changing historical records."""
from alembic import op
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_index("ix_received_mission_ingested_id", "received_events", ["mission_id", "ingested_at", "id"])

def downgrade() -> None:
    op.drop_index("ix_received_mission_ingested_id", table_name="received_events")
