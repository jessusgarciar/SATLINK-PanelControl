import base64
import binascii
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from collections.abc import AsyncIterator
from uuid import UUID, uuid4
from sqlalchemy import select, tuple_, func, Select
from sqlalchemy.ext.asyncio import AsyncResult, AsyncSession
from anyio import CancelScope
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.domain.entities.telemetry import ConfigurationConflict, IncomingUplink, JsonObject, Mission, MissionNotFound, observed_application_name
from app.infrastructure.database.models import MissionRow, ReceivedEventRow, TelemetryRow, PredictionAttemptRow, CommandRow
from app.domain.entities.commands import CommandConflict, COMMAND_TYPES
from app.domain.entities.prediction import PredictionCooldown
from app.infrastructure.mqtt.metadata import enrich_telemetry
from app.application.use_cases.query_telemetry import interval
from app.domain.entities.radiosonda import flight_state, command_result


def iso(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).isoformat()


def archive_response(value: JsonObject | None) -> JsonObject | None:
    """JSON inválido se archiva como texto escapado, nunca como constantes JSONB."""
    if value is None:
        return None
    try:
        serialized = json.dumps(value, ensure_ascii=True, allow_nan=False)
        # JSONB rechaza NUL y sustitutos aislados; el texto conserva los escapes.
        if re.search(r"\\u(?:0000|d[89a-f][0-9a-f]{2})", serialized):
            raise ValueError("Texto incompatible con JSONB")
        return value
    except (ValueError, TypeError):
        return {"invalidJson": json.dumps(value, ensure_ascii=True, default=str)[:262144]}


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

    @asynccontextmanager
    async def edit_mission(self, mission_id: str) -> AsyncIterator[tuple[JsonObject, JsonObject]]:
        async with self.sessions.begin() as session:
            row = await session.scalar(select(MissionRow).where(MissionRow.id == mission_id).with_for_update())
            if row is None:
                raise MissionNotFound(mission_id)
            configuration, snapshot = dict(row.configuration), dict(row.snapshot)
            yield configuration, snapshot
            row.configuration, row.snapshot = configuration, snapshot

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
                if row is None:
                    raise ConfigurationConflict("La misión existe con otra configuración; no se modificó su origen")
                if row.configuration != config:
                    previous = dict(row.configuration)
                    requested = dict(config)
                    for key in ("applicationName", "plannedLaunchAt"):
                        previous.setdefault(key, None)
                        requested.setdefault(key, None)
                    for key, default in (("telemetryProtocol", "legacy"), ("altitudeTargetMode", "relative")):
                        previous.setdefault(key, default)
                        requested.setdefault(key, default)
                        previous.pop(key)
                        requested.pop(key)
                    previous.pop("applicationName", None)
                    requested.pop("applicationName", None)
                    previous.pop("staleAfterSeconds", None)
                    requested_staleness = requested.pop("staleAfterSeconds", None)
                    if previous != requested:
                        raise ConfigurationConflict(
                            "La misión existe con otra configuración; no se modificó su origen")
                    row.configuration = config
                    row.snapshot = {**row.snapshot, "staleAfterSeconds": requested_staleness,
                                    "telemetryProtocol": config.get("telemetryProtocol", "legacy"),
                                    "altitudeTargetMode": config.get("altitudeTargetMode", "relative"),
                                    "applicationName": config.get("applicationName"),
                                    "updatedAt": datetime.now(timezone.utc).isoformat()}
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
                details={"codec": event.metadata, "measurements": event.measurements,
                         "event": event.raw_event, "provenance": "chirpstack"},
            ).on_conflict_do_nothing(constraint="uq_received_event").returning(ReceivedEventRow.id))
            if inserted is None:
                return False
            packet = telemetry.get("packet")
            control = packet and packet["fPort"] in (30, 31)
            if not control:
                session.add(TelemetryRow(id=telemetry["id"], mission_id=mission.id,
                                          received_at=event.received_at, data=dict(telemetry)))
            if packet and packet["fPort"] in (23, 30, 31):
                row = await session.scalar(select(MissionRow).where(MissionRow.id == mission.id).with_for_update())
                if packet["fPort"] in (23, 31):
                    state = flight_state(row.snapshot.get("flightState"), packet, event.received_at)
                    row.snapshot = {**row.snapshot, "flightState": state, "updatedAt": datetime.now(timezone.utc).isoformat()}
                if control and (packet["fPort"] == 30 or packet.get("motivo") == "downlink"):
                    kind = "PING" if packet["fPort"] == 30 else "RELEASE_NOW"
                    candidates = (await session.scalars(select(CommandRow).where(
                        CommandRow.mission_id == mission.id, CommandRow.kind == kind,
                        CommandRow.created_at <= event.received_at,
                        CommandRow.created_at >= event.received_at - timedelta(minutes=15),
                        CommandRow.status.in_(("pending", "sent", "received")),
                        CommandRow.data["seq"].as_integer() == packet["seq"]))).all()
                    if len(candidates) == 1:
                        command = candidates[0]
                        status, evidence, result = command_result(packet, command.created_at, event.received_at)
                        prior = command.data.get("feedbackAt")
                        if prior is None or datetime.fromisoformat(prior) < event.received_at:
                            command.status = status
                            command.data = {**command.data, "status": status, "evidence": evidence,
                                            "result": result, "feedbackAt": event.received_at.isoformat(),
                                            "updatedAt": datetime.now(timezone.utc).isoformat()}
                            telemetry["_commandUpdates"] = [command.data]
            name = observed_application_name(event.raw_event)
            if name and mission.snapshot.get("applicationName") != name:
                row = await session.scalar(select(MissionRow).where(MissionRow.id == mission.id).with_for_update())
                if row is not None and row.snapshot.get("applicationName") != name:
                    latest = await session.scalar(select(func.max(TelemetryRow.received_at)).where(
                        TelemetryRow.mission_id == mission.id))
                    if latest is None or event.received_at >= latest:
                        row.configuration = {**row.configuration, "applicationName": name}
                        row.snapshot = {**row.snapshot, "applicationName": name,
                                        "updatedAt": datetime.now(timezone.utc).isoformat()}
        return True

    async def reject(self, source: str, topic: str, payload: bytes, reason: str) -> None:
        # Asociar únicamente a la identidad del topic; el JSON rechazado no es confiable.
        match = re.fullmatch(r"application/([^/+#]+)/device/([0-9a-fA-F]{16})/event/up", topic)
        mission = await self.find_mission(source, match[1], match[2].lower()) if match else None
        async with self.sessions.begin() as session:
            session.add(ReceivedEventRow(
                id=str(uuid4()), source=source, mission_id=mission.id if mission else None, dev_eui=match[2].lower() if match else None, deduplication_id=None,
                received_at=None, ingested_at=datetime.now(timezone.utc), status="rejected",
                reason=reason[:512], raw_payload=payload[:262144],
                details={"topic": topic[:1024], "originalSize": len(payload), "truncated": len(payload) > 262144},
            ))

    async def dashboard(self, mission_id: str, limit: int = 1200) -> JsonObject:
        if not 1 <= limit <= 1200:
            raise ValueError("limit debe estar entre 1 y 1200")
        async with self.sessions.begin() as session:
            mission = await session.get(MissionRow, mission_id)
            if mission is None:
                raise MissionNotFound(mission_id)
            if mission.snapshot.get("telemetryProtocol") == "radiosonda-v1":
                await session.refresh(mission, with_for_update=True)
                await self._expire_radio_commands(session, mission_id, datetime.now(timezone.utc))
            rows = (await session.execute(filtered_rows(mission_id, None, None).order_by(
                TelemetryRow.received_at.desc(), TelemetryRow.id.desc()).limit(limit))).all()
            samples = [enrich_telemetry(data, details) for data, details, _ in rows]
            observed_name = next((name for _, details, _ in rows
                                  if isinstance(details, dict) and isinstance(details.get("event"), dict)
                                  and (name := observed_application_name(details["event"]))), None)
            prediction = await session.scalar(select(PredictionAttemptRow.normalized).where(
                PredictionAttemptRow.mission_id == mission_id, PredictionAttemptRow.status == "succeeded"
            ).order_by(PredictionAttemptRow.requested_at.desc(), PredictionAttemptRow.id.desc()).limit(1))
            next_allowed = await session.scalar(select(func.max(PredictionAttemptRow.next_allowed_at)).where(
                PredictionAttemptRow.mission_id == mission_id))
            commands = (await session.scalars(select(CommandRow.data).where(CommandRow.mission_id == mission_id)
                .order_by(CommandRow.created_at.desc(), CommandRow.id.desc()).limit(100))).all()
            return {"mission": {**mission.snapshot, "applicationId": mission.application_id,
                                "applicationName": mission.snapshot.get("applicationName") or observed_name or mission.configuration.get("applicationName"),
                                "plannedLaunchAt": mission.configuration.get("plannedLaunchAt")}, "telemetry": list(reversed(samples)),
                    "commands": list(commands), "events": [], "prediction": prediction,
                    "predictionHistory": await self._prediction_history(session, mission_id),
                    "permissions": {"canCommand": False, "canPredict": False}, "csrfToken": None,
                    "predictionSettings": {"enabled": False, "launchAltitudeReference": "unknown",
                                           "gpsAltitudeReference": "unknown", "nextAllowedAt": iso(next_allowed)},
                    "ingestion": {"source": mission.source, "status": "disabled",
                                  "updatedAt": datetime.now(timezone.utc).isoformat()}}

    async def packets(self, mission_id: str, cursor: str | None = None, limit: int = 50) -> JsonObject:
        if not 1 <= limit <= 100:
            raise ValueError("Límite de paquetes inválido")
        async with self.sessions() as session:
            if await session.get(MissionRow, mission_id) is None:
                raise MissionNotFound(mission_id)
            query = select(ReceivedEventRow).where(ReceivedEventRow.mission_id == mission_id)
            if cursor:
                try:
                    stamp, identifier = json.loads(base64.urlsafe_b64decode(cursor).decode())
                    stamp = datetime.fromisoformat(stamp)
                    if stamp.tzinfo is None:
                        raise ValueError()
                    identifier = str(UUID(identifier))
                except (ValueError, TypeError, binascii.Error, UnicodeError) as exc:
                    raise ValueError("Cursor de paquetes inválido") from exc
                query = query.where(tuple_(ReceivedEventRow.ingested_at, ReceivedEventRow.id) < tuple_(stamp, identifier))
            rows = (await session.scalars(query.order_by(ReceivedEventRow.ingested_at.desc(), ReceivedEventRow.id.desc()).limit(limit + 1))).all()
            page = rows[:limit]
            items = []
            for row in page:
                raw = row.details.get("event")
                if raw is None:
                    try:
                        raw = json.loads(row.raw_payload)
                    except (ValueError, UnicodeError):
                        raw = {"unparsedText": row.raw_payload.decode("utf-8", errors="replace")}
                items.append({"id": row.id, "receivedAt": iso(row.received_at), "ingestedAt": iso(row.ingested_at),
                    "status": row.status, "reason": row.reason, "decoded": {**row.details.get("measurements", {}), **row.details.get("codec", {})},
                    "raw": archive_response(raw) if isinstance(raw, dict) else {"value": str(raw)},
                    "rawBase64": base64.b64encode(row.raw_payload).decode()})
            last = page[-1] if len(rows) > limit else None
            next_cursor = base64.urlsafe_b64encode(json.dumps([iso(last.ingested_at), last.id]).encode()).decode() if last else None
            return {"items": items, "nextCursor": next_cursor}

    async def _expire_radio_commands(self, session: AsyncSession, mission_id: str, now: datetime) -> None:
        expired = (await session.scalars(select(CommandRow).where(CommandRow.mission_id == mission_id,
            CommandRow.status.in_(("pending", "sent", "received")),
            CommandRow.created_at < now - timedelta(minutes=15)))).all()
        for old in expired:
            old.status = "expired"
            old.data = {**old.data, "status": "expired", "updatedAt": iso(now),
                        "evidence": "Ventana de respuesta agotada; ejecución no confirmada. Sin reenvío automático."}
        await session.flush()

    async def reserve_command(self, mission_id: str, request_id: str, kind: str,
                              now: datetime) -> tuple[JsonObject, bool]:
        if kind not in COMMAND_TYPES:
            raise CommandConflict("Tipo de comando no implementado")
        async with self.sessions.begin() as session:
            mission = await session.scalar(select(MissionRow).where(MissionRow.id == mission_id).with_for_update())
            if mission is None:
                raise MissionNotFound(mission_id)
            previous = await session.scalar(select(CommandRow).where(
                CommandRow.mission_id == mission_id, CommandRow.client_request_id == request_id))
            if previous is not None:
                if previous.kind != kind:
                    raise CommandConflict("Idempotency-Key ya utilizada para otro comando")
                return previous.data, False
            if kind == "START_MISSION" and mission.snapshot.get("startedAt"):
                raise CommandConflict("La misión ya está iniciada; no se reinició el watchdog")
            if mission.snapshot.get("telemetryProtocol") == "radiosonda-v1":
                await self._expire_radio_commands(session, mission_id, now)
            active = await session.scalar(select(CommandRow.id).where(CommandRow.mission_id == mission_id,
                CommandRow.kind == kind, CommandRow.status.in_(("pending", "sent", "received"))).limit(1))
            if active:
                raise CommandConflict("Ya existe una solicitud activa de este comando; revisar bitácora")
            latest = await session.scalar(select(func.max(TelemetryRow.received_at)).where(TelemetryRow.mission_id == mission_id))
            # PING/STATUS/TELEM permiten diagnosticar aun sin muestras. El inicio requiere datos recientes.
            if kind == "START_MISSION" and (latest is None or not -5 <= (now - latest).total_seconds() <= mission.snapshot["staleAfterSeconds"]):
                raise CommandConflict("Iniciar misión requiere telemetría reciente de esta Heltec")
            identifier = str(uuid4())
            data = {"id": identifier, "missionId": mission_id, "clientRequestId": request_id, "type": kind,
                    "status": "pending", "createdAt": iso(now), "updatedAt": iso(now),
                    "evidence": "Solicitud persistida; todavía no confirma recepción ni ejecución.", "simulated": False,
                    "watchdogSeconds": mission.snapshot["watchdogSeconds"]}
            if mission.snapshot.get("telemetryProtocol") == "radiosonda-v1":
                if kind not in ("PING", "RELEASE_NOW"):
                    raise CommandConflict("La radiosonda solo admite Marco y corte; el inicio es autónomo")
                if kind == "RELEASE_NOW" and (latest is None or not -5 <= (now - latest).total_seconds() <= mission.snapshot["staleAfterSeconds"]):
                    raise CommandConflict("El corte requiere telemetría reciente de esta sonda")
                recent = (await session.scalars(select(CommandRow).where(CommandRow.mission_id == mission_id))).all()
                used = {c.data.get("seq") for c in recent}
                available = next((s for s in range(1, 256) if s not in used), None)
                if available is None:
                    raise CommandConflict("Secuencias agotadas para esta misión; no se reutilizó ninguna")
                data["seq"] = available
            session.add(CommandRow(id=identifier, mission_id=mission_id, client_request_id=request_id,
                kind=kind, status="pending", created_at=now, data=data))
        return data, True

    async def command_evidence(self, mission_id: str, command_id: str, status: str,
                               evidence: str, *, started_at: datetime | None = None) -> tuple[JsonObject, JsonObject | None]:
        ranks = {"pending": 0, "sent": 1, "received": 2, "executed": 3, "rejected": 3, "expired": 3}
        if status not in ranks or not evidence.strip():
            raise CommandConflict("Estado o evidencia inválidos")
        updated_mission = None
        async with self.sessions.begin() as session:
            mission = await session.scalar(select(MissionRow).where(MissionRow.id == mission_id).with_for_update())
            if mission is None:
                raise MissionNotFound(mission_id)
            row = await session.scalar(select(CommandRow).where(CommandRow.id == command_id,
                CommandRow.mission_id == mission_id).with_for_update())
            if row is None:
                raise CommandConflict("Comando inexistente para esta misión")
            if ranks[row.status] == 3 or ranks[status] < ranks[row.status]:
                return row.data, None
            now = datetime.now(timezone.utc)
            if row.kind == "START_MISSION" and status == "executed":
                if (started_at is None or started_at.tzinfo is None or
                        started_at < row.created_at or started_at > now + timedelta(seconds=5)):
                    raise CommandConflict("El inicio requiere fecha válida de ejecución confirmada por firmware")
                if mission.snapshot.get("startedAt"):
                    raise CommandConflict("La misión ya tiene un inicio confirmado")
                mission.snapshot = {**mission.snapshot, "startedAt": iso(started_at), "updatedAt": iso(now)}
                updated_mission = {**mission.snapshot, "applicationId": mission.application_id}
            elif started_at is not None:
                raise CommandConflict("Solo la ejecución de START_MISSION puede fijar el inicio")
            row.status = status
            row.data = {**row.data, "status": status, "evidence": evidence[:2048], "updatedAt": iso(now)}
            data = row.data
        return data, updated_mission

    async def prediction_context(self, mission_id: str) -> JsonObject:
        snapshot = await self.dashboard(mission_id, 1200)
        samples = snapshot["telemetry"]
        latest = next((s for s in reversed(samples) if not s.get("packet") or
                       "latitude" in s["packet"].get("presentFields", [])), None)
        return {"mission": snapshot["mission"],
                "telemetry": latest}

    async def reserve_prediction(self, mission_id: str, request: JsonObject, now: datetime) -> str:
        attempt_id = str(uuid4())
        async with self.sessions.begin() as session:
            # Bloqueo por misión únicamente durante reserva, nunca durante HTTP.
            mission = await session.scalar(select(MissionRow).where(
                MissionRow.id == mission_id).with_for_update())
            if mission is None:
                raise MissionNotFound(mission_id)
            next_allowed = await session.scalar(select(func.max(PredictionAttemptRow.next_allowed_at)).where(
                PredictionAttemptRow.mission_id == mission_id))
            if next_allowed is not None and next_allowed > now:
                raise PredictionCooldown(next_allowed)
            session.add(PredictionAttemptRow(id=attempt_id, mission_id=mission_id,
                requested_at=now, next_allowed_at=now + timedelta(seconds=60), status="pending",
                raw_request=request, raw_response=None, normalized=None, error=None))
        return attempt_id

    async def complete_prediction(self, attempt_id: str, raw_response: JsonObject,
                                  normalized: JsonObject) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(PredictionAttemptRow, attempt_id)
            if row is None:
                raise LookupError("Intento de predicción inexistente")
            row.status, row.raw_response, row.normalized, row.error = "succeeded", archive_response(raw_response), normalized, None

    async def fail_prediction(self, attempt_id: str, reason: str,
                             raw_response: JsonObject | None = None) -> None:
        async with self.sessions.begin() as session:
            row = await session.get(PredictionAttemptRow, attempt_id)
            if row is None:
                raise LookupError("Intento de predicción inexistente")
            row.status, row.error, row.raw_response = "failed", reason[:128], archive_response(raw_response)

    async def latest_prediction(self, mission_id: str) -> JsonObject | None:
        async with self.sessions() as session:
            return await session.scalar(select(PredictionAttemptRow.normalized).where(
                PredictionAttemptRow.mission_id == mission_id, PredictionAttemptRow.status == "succeeded"
            ).order_by(PredictionAttemptRow.requested_at.desc(), PredictionAttemptRow.id.desc()).limit(1))

    async def _prediction_history(self, session, mission_id: str) -> list[JsonObject]:
        history = []
        for mode in ("planned", "ascending"):
            rows = await session.scalars(select(PredictionAttemptRow.normalized).where(
                PredictionAttemptRow.mission_id == mission_id,
                PredictionAttemptRow.status == "succeeded",
                PredictionAttemptRow.normalized["context"]["mode"].as_string() == mode,
            ).order_by(PredictionAttemptRow.requested_at.desc(), PredictionAttemptRow.id.desc()).limit(2))
            history.extend(rows.all())
        return history

    async def prediction_history(self, mission_id: str) -> list[JsonObject]:
        async with self.sessions() as session:
            return await self._prediction_history(session, mission_id)

    async def prediction_next_allowed_at(self, mission_id: str) -> datetime | None:
        async with self.sessions() as session:
            return await session.scalar(select(func.max(PredictionAttemptRow.next_allowed_at)).where(
                PredictionAttemptRow.mission_id == mission_id))

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
