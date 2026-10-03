import base64
import binascii
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.domain.entities.telemetry import ConfigurationConflict, IncomingUplink, JsonObject, Mission, MissionNotFound
from app.infrastructure.database.models import MissionRow, ReceivedEventRow, TelemetryRow


def iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).isoformat()


class PostgresStore:
    def __init__(self, database_url: str) -> None:
        self.engine = create_async_engine(database_url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def close(self) -> None:
        await self.engine.dispose()

    async def initialize_mission(self, config: JsonObject) -> JsonObject:
        snapshot = {k: v for k, v in config.items() if k not in ("source", "applicationId")}
        snapshot.update(updatedAt=datetime.now(timezone.utc).isoformat(), startedAt=None,
                        endedAt=None, phase="unknown", beaconOn=None)
        try:
            async with self.sessions.begin() as session:
                await session.execute(insert(MissionRow).values(
                    id=config["id"], source=config["source"], application_id=config["applicationId"],
                    dev_eui=config["deviceEui"], configuration=config, snapshot=snapshot,
                ).on_conflict_do_nothing(index_elements=["id"]))
                row = await session.get(MissionRow, config["id"])
                if row is None or row.configuration != config:
                    raise ConfigurationConflict("La misión existe con otra configuración; no se modificó su origen")
                return row.snapshot
        except IntegrityError as exc:
            raise ConfigurationConflict("El dispositivo ya está asociado a otra misión") from exc

    async def find_mission(self, source: str, application_id: str, dev_eui: str) -> Mission | None:
        async with self.sessions() as session:
            row = (await session.scalars(select(MissionRow).where(
                MissionRow.source == source, MissionRow.application_id == application_id,
                MissionRow.dev_eui == dev_eui))).one_or_none()
            return None if row is None else Mission(row.id, row.source, row.application_id, row.dev_eui, row.snapshot)

    async def persist(self, mission: Mission, event: IncomingUplink, telemetry: JsonObject) -> bool:
        async with self.sessions.begin() as session:
            inserted = await session.scalar(insert(ReceivedEventRow).values(
                id=telemetry["id"], source=event.source, mission_id=mission.id, dev_eui=event.dev_eui,
                deduplication_id=event.deduplication_id, received_at=event.received_at,
                ingested_at=datetime.now(timezone.utc), status="accepted", reason=None,
                raw_payload=event.raw_payload,
                details={"codec": event.metadata, "event": event.raw_event, "provenance": "chirpstack"},
            ).on_conflict_do_nothing(constraint="uq_received_event").returning(ReceivedEventRow.id))
            if inserted is None:
                return False
            session.add(TelemetryRow(id=telemetry["id"], mission_id=mission.id,
                                     received_at=event.received_at, data=telemetry))
        return True

    async def reject(self, source: str, topic: str, payload: bytes, reason: str) -> None:
        async with self.sessions.begin() as session:
            session.add(ReceivedEventRow(
                id=str(uuid4()), source=source, mission_id=None, dev_eui=None, deduplication_id=None,
                received_at=None, ingested_at=datetime.now(timezone.utc), status="rejected",
                reason=reason[:512], raw_payload=payload[:262144],
                details={"topic": topic[:1024], "originalSize": len(payload), "truncated": len(payload) > 262144},
            ))

    async def dashboard(self, mission_id: str, limit: int = 1200) -> JsonObject:
        if not 1 <= limit <= 1200:
            raise ValueError("limit debe estar entre 1 y 1200")
        async with self.sessions() as session:
            mission = await session.get(MissionRow, mission_id)
            if mission is None:
                raise MissionNotFound(mission_id)
            samples = list((await session.scalars(select(TelemetryRow.data).where(
                TelemetryRow.mission_id == mission_id).order_by(
                TelemetryRow.received_at.desc(), TelemetryRow.id.desc()).limit(limit))).all())
            return {"mission": mission.snapshot, "telemetry": list(reversed(samples)),
                    "commands": [], "events": [], "prediction": None,
                    "permissions": {"canCommand": False, "canPredict": False}, "csrfToken": None}

    async def history(self, mission_id: str, from_time: datetime | None = None,
                      to_time: datetime | None = None, cursor: str | None = None,
                      limit: int = 200) -> JsonObject:
        if not 1 <= limit <= 1200:
            raise ValueError("limit debe estar entre 1 y 1200")
        if any(t is not None and t.tzinfo is None for t in (from_time, to_time)):
            raise ValueError("Se requiere zona horaria")
        if from_time is not None and to_time is not None and from_time >= to_time:
            raise ValueError("from debe ser anterior a to")
        scope = {"mission": mission_id, "from": iso(from_time), "to": iso(to_time)}
        statement = select(TelemetryRow).where(TelemetryRow.mission_id == mission_id)
        if from_time is not None:
            statement = statement.where(TelemetryRow.received_at >= from_time)
        if to_time is not None:
            statement = statement.where(TelemetryRow.received_at < to_time)
        if cursor is not None:
            try:
                if len(cursor) > 2048:
                    raise ValueError()
                state = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                if not isinstance(state, dict) or any(state.get(k) != v for k, v in scope.items()):
                    raise ValueError()
                last_time = datetime.fromisoformat(state["time"])
                if last_time.tzinfo is None:
                    raise ValueError()
                last_id = str(UUID(state["id"]))
            except (ValueError, TypeError, KeyError, binascii.Error, UnicodeError) as exc:
                raise ValueError("Cursor inválido o ajeno a estos filtros") from exc
            statement = statement.where(tuple_(TelemetryRow.received_at, TelemetryRow.id) > tuple_(last_time, last_id))
        async with self.sessions() as session:
            if await session.get(MissionRow, mission_id) is None:
                raise MissionNotFound(mission_id)
            rows = list((await session.scalars(statement.order_by(
                TelemetryRow.received_at, TelemetryRow.id).limit(limit + 1))).all())
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                state = {**scope, "time": iso(last.received_at), "id": last.id}
                next_cursor = base64.urlsafe_b64encode(json.dumps(state).encode()).decode()
            return {"items": [r.data for r in rows[:limit]], "nextCursor": next_cursor}
