import base64
import binascii
import json
from datetime import datetime, timezone
from collections.abc import AsyncIterator
from uuid import UUID, uuid4
from sqlalchemy import select, tuple_, func, Select
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from anyio import CancelScope
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.domain.entities.telemetry import ConfigurationConflict, IncomingUplink, JsonObject, Mission, MissionNotFound
from app.infrastructure.database.models import MissionRow, ReceivedEventRow, TelemetryRow
from app.infrastructure.mqtt.metadata import enrich_telemetry
from app.application.use_cases.query_telemetry import interval


def iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).isoformat()


def selected_indices(total: int, maximum: int) -> set[int]:
    if total <= maximum:
        return set(range(total))
    # Se agregó este muestreo ya que en el Ejercicio 10 el historial permite revisar todo el vuelo.
    return {i * (total - 1) // (maximum - 1) for i in range(maximum)}


def filtered_rows(mission_id: str, start: datetime | None, end: datetime | None) -> Select:
    statement = select(TelemetryRow.data, ReceivedEventRow.details, ReceivedEventRow.source).join(
        ReceivedEventRow, ReceivedEventRow.id == TelemetryRow.id).where(TelemetryRow.mission_id == mission_id)
    if start is not None:
        statement = statement.where(TelemetryRow.received_at >= start)
    if end is not None:
        statement = statement.where(TelemetryRow.received_at < end)
    return statement


class DatabaseExport:
    def __init__(self, session: AsyncSession, result: AsyncResult) -> None:
        self.session, self.result = session, result
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[JsonObject]:
        try:
            async for data, details, source, application_id, dev_eui in self.result:
                yield {"telemetry": enrich_telemetry(data, details), "source": source,
                       "applicationId": application_id, "devEui": dev_eui,
                       "raw_json": details.get("event") if isinstance(details, dict) else None}
        finally:
            await self.aclose()

    async def aclose(self) -> None:
        if self.closed:
            return
        self.closed = True
        # La desconexión HTTP puede cancelar la tarea: cerrar también bajo ese cancel scope.
        with CancelScope(shield=True):
            try:
                await self.result.close()
            finally:
                await self.session.close()


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
            rows = (await session.execute(filtered_rows(mission_id, None, None).order_by(
                TelemetryRow.received_at.desc(), TelemetryRow.id.desc()).limit(limit))).all()
            samples = [enrich_telemetry(data, details) for data, details, _ in rows]
            return {"mission": mission.snapshot, "telemetry": list(reversed(samples)),
                    "commands": [], "events": [], "prediction": None,
                    "permissions": {"canCommand": False, "canPredict": False}, "csrfToken": None,
                    "ingestion": {"source": mission.source, "status": "disabled",
                                  "updatedAt": datetime.now(timezone.utc).isoformat()}}

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
        statement = filtered_rows(mission_id, from_time, to_time).add_columns(TelemetryRow.received_at,
                                                                           TelemetryRow.id)
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
            rows = list((await session.execute(statement.order_by(
                TelemetryRow.received_at, TelemetryRow.id).limit(limit + 1))).all())
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                state = {**scope, "time": iso(last[3]), "id": last[4]}
                next_cursor = base64.urlsafe_b64encode(json.dumps(state).encode()).decode()
            return {"items": [enrich_telemetry(r[0], r[1]) for r in rows[:limit]], "nextCursor": next_cursor}

    async def window(self, mission_id: str, from_time: datetime | None,
                     to_time: datetime) -> JsonObject:
        interval(from_time, to_time)
        async with self.sessions() as session:
            # El conteo y el cursor comparten snapshot, incluso si llega telemetría durante la consulta.
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            if await session.get(MissionRow, mission_id) is None:
                raise MissionNotFound(mission_id)
            query = filtered_rows(mission_id, from_time, to_time)
            total = int(await session.scalar(select(func.count()).select_from(query.subquery())) or 0)
            gps_query = query.where(TelemetryRow.data["latitude"].as_float().is_not(None),
                                    TelemetryRow.data["longitude"].as_float().is_not(None))
            gps_total = int(await session.scalar(select(func.count()).select_from(gps_query.subquery())) or 0)
            series_indices = selected_indices(total, 600)
            track_indices = selected_indices(gps_total, 500)
            series, track, gps_index = [], [], 0
            result = await session.stream(query.order_by(TelemetryRow.received_at, TelemetryRow.id),
                                          execution_options={"yield_per": 200})
            try:
                index = 0
                async for data, details, _ in result:
                    point = None
                    if index in series_indices:
                        point = enrich_telemetry(data, details)
                        series.append(point)
                    if data.get("latitude") is not None and data.get("longitude") is not None:
                        if gps_index in track_indices:
                            track.append(point if point is not None else enrich_telemetry(data, details))
                        gps_index += 1
                    index += 1
            finally:
                await result.close()
            return {"from": iso(from_time), "to": iso(to_time), "total": total,
                    "series": series, "track": track}

    async def export(self, mission_id: str, from_time: datetime | None,
                     to_time: datetime) -> DatabaseExport:
        interval(from_time, to_time)
        session = self.sessions()
        try:
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
            if await session.get(MissionRow, mission_id) is None:
                raise MissionNotFound(mission_id)
            query = filtered_rows(mission_id, from_time, to_time).join(
                MissionRow, MissionRow.id == TelemetryRow.mission_id).add_columns(
                    MissionRow.application_id, ReceivedEventRow.dev_eui).order_by(
                TelemetryRow.received_at, TelemetryRow.id)
            result = await session.stream(query, execution_options={"yield_per": 200})
            return DatabaseExport(session, result)
        except BaseException:
            with CancelScope(shield=True):
                await session.close()
            raise
