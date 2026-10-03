from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, String, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class MissionRow(Base):
    __tablename__ = "missions"
    __table_args__ = (UniqueConstraint("source", "application_id", "dev_eui", name="uq_mission_device"),)
    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(128))
    application_id: Mapped[str] = mapped_column(String(128))
    dev_eui: Mapped[str] = mapped_column(String(16))
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ReceivedEventRow(Base):
    __tablename__ = "received_events"
    __table_args__ = (
        UniqueConstraint("source", "dev_eui", "deduplication_id", name="uq_received_event"),
        CheckConstraint("status IN ('accepted','rejected')", name="ck_received_status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(128))
    mission_id: Mapped[str | None] = mapped_column(ForeignKey("missions.id"))
    dev_eui: Mapped[str | None] = mapped_column(String(16))
    deduplication_id: Mapped[str | None] = mapped_column(String(36))
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(512))
    raw_payload: Mapped[bytes] = mapped_column(LargeBinary)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)


class TelemetryRow(Base):
    __tablename__ = "telemetry"
    __table_args__ = (Index("ix_telemetry_mission_time_id", "mission_id", "received_at", "id"),)
    id: Mapped[str] = mapped_column(ForeignKey("received_events.id"), primary_key=True)
    mission_id: Mapped[str] = mapped_column(ForeignKey("missions.id"))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
