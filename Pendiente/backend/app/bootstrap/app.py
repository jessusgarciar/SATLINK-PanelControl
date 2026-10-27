import asyncio
import secrets
import math
import json
from pathlib import Path
from datetime import datetime, timezone
from contextlib import asynccontextmanager, contextmanager, suppress
from typing import Annotated, AsyncIterator, Iterator
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from app.application.use_cases.ingest import IngestTelemetry
from app.application.use_cases.ingestion_state import IngestionState
from app.application.use_cases.query_telemetry import QueryTelemetry
from app.bootstrap.config import Settings
from app.bootstrap.demo import DEMO_MISSION
from app.domain.entities.telemetry import MissionNotFound, ConfigurationConflict
from app.domain.entities.telemetry import JsonObject
from app.infrastructure.database.store import PostgresStore
from app.infrastructure.mqtt.consumer import consume
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.api.local import LocalOnlyMiddleware
from app.presentation.api.streaming import CsvStreamingResponse
from app.presentation.schemas.api import DashboardDTO, HistoryDTO, WindowDTO, MissionDTO, MissionParameters, PacketPageDTO
from app.infrastructure.mission_settings import MissionSettings
from app.presentation.schemas.uplink import ChirpStackDecoder, utc_time
from app.presentation.websocket.hub import TelemetryHub
from app.application.ports.prediction import PredictionProvider
from app.application.use_cases.predict import PredictMission
from app.domain.entities.prediction import PredictionCooldown, PredictionInvalid, PredictionTimeout, PredictionUnavailable
from app.infrastructure.prediction.tawhiri import TawhiriProvider
from app.presentation.schemas.prediction import PredictionDTO, PredictionRequest, DemoPredictionRequest, DemoPredictionSession
from app.application.ports.commands import CommandTransport
from app.application.use_cases.commands import RequestCommand
from app.domain.entities.commands import COMMAND_TYPES, CommandConflict, CommandUnavailable
from app.infrastructure.mqtt.commands import CommandProfile, ChirpStackCommands
from app.presentation.schemas.commands import CommandRequest, CommandDTO


def create_app(settings: Settings, store: PostgresStore | None = None,
               publisher: TelemetryHub | None = None, *,
               prediction_provider: PredictionProvider | None = None,
               mqtt_topic: str | None = None, mission_path: Path | None = None,
               command_transport: CommandTransport | None = None) -> FastAPI:
    if settings.mqtt_enabled and not mqtt_topic:
        raise ValueError("El topic MQTT de la misión es obligatorio cuando MQTT está habilitado")
    repository = store if store is not None else PostgresStore(settings.database_url)
    hub = publisher if publisher is not None else TelemetryHub()
    ingestor = IngestTelemetry(repository, hub, settings.source, ChirpStackDecoder(decode_payload))
    ingestion = IngestionState(settings.source, settings.mqtt_enabled, hub)
    queries = QueryTelemetry(repository)
    provider = prediction_provider
    if provider is None and (settings.prediction_enabled or settings.demo_prediction_enabled):
        provider = TawhiriProvider(settings.prediction_url)
    predictor = None if provider is None else PredictMission(repository, provider, hub)
    csrf_token = secrets.token_urlsafe(32)
    mission_settings = MissionSettings(repository, mission_path or Path(__file__).resolve().parents[2] / "mission.local.json")
    mqtt_commands = None
    if settings.command_profile_file:
        path = Path(settings.command_profile_file)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        profile = CommandProfile.load(path)
        expected_topic = f"application/{profile.application_id}/device/{profile.device_eui}/event/up"
        if not settings.mqtt_enabled or settings.source != profile.source or mqtt_topic != expected_topic:
            raise ValueError("El perfil de comandos debe coincidir con el origen y topic de la misión activa")
        mqtt_commands = ChirpStackCommands(settings, profile)
        command_transport = mqtt_commands
    elif settings.mqtt_enabled:
        path = mission_path or Path(__file__).resolve().parents[2] / "mission.local.json"
        local = json.loads(path.read_text(encoding="utf-8-sig"))
        if local.get("telemetryProtocol") == "radiosonda-meca-v1":
            expected = f"application/{local['applicationId']}/device/{local['deviceEui']}/event/up"
            if mqtt_topic != expected or local["source"] != settings.source:
                raise ValueError("Identidad radiosonda no coincide con la suscripción MQTT")
            profile = CommandProfile(local["id"], local["applicationId"], local["deviceEui"], local["source"],
                                     30, {"PING": "", "RELEASE_NOW": ""}, "radiosonda-meca-v1")
            mqtt_commands = ChirpStackCommands(settings, profile)
            command_transport = mqtt_commands
    commander = RequestCommand(repository, hub, command_transport)

    async def ingest(topic: str, payload: bytes) -> object:
        if mqtt_commands is not None and topic in mqtt_commands.event_topics:
            return await mqtt_commands.ingest_evidence(topic, payload, commander)
        return await ingestor.execute(topic, payload)

    def source_of(snapshot: dict) -> str:
        metadata = snapshot.get("ingestion") or {}
        return metadata.get("source", settings.source)

    @contextmanager
    def subscription(mission_id: str, source: str) -> Iterator[asyncio.Queue[JsonObject | None]]:
        try:
            with hub.subscribe(mission_id) as queue:
                if source == settings.source:
                    ingestion.missions.add(mission_id)
                yield queue
        finally:
            if mission_id not in hub.clients:
                ingestion.missions.discard(mission_id)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = None
        try:
            if settings.demo_prediction_enabled:
                await repository.initialize_mission(DEMO_MISSION)
            if settings.mqtt_enabled:
                task = asyncio.create_task(consume(settings.mqtt_host, settings.mqtt_port,
                    settings.mqtt_username, settings.mqtt_password, settings.mqtt_tls,
                    settings.mqtt_client_id, mqtt_topic, ingest, ingestion.update,
                    *([mqtt_commands.event_topics] if mqtt_commands is not None else [])))
            yield
        finally:
            try:
                if task is not None:
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        await task
                    await ingestion.update("offline")
            finally:
                try:
                    await repository.close()
                finally:
                    if provider is not None:
                        await provider.close()

    app = FastAPI(title="SATLINK · Telemetría local", version="1.0.0", lifespan=lifespan)
    app.add_middleware(LocalOnlyMiddleware, allowed_origins=settings.allowed_origins)
    app.state.ingestor, app.state.store, app.state.hub = ingestor, repository, hub
    app.state.ingestion = ingestion
    app.state.prediction_csrf_token = csrf_token
    app.state.predictor = predictor
    app.state.commander = commander

    @app.get("/api/v1/missions/{mission_id}/dashboard", response_model=DashboardDTO)
    async def dashboard(mission_id: str, limit: Annotated[int, Query(ge=1, le=1200)] = 1200) -> dict:
        try:
            snapshot = await repository.dashboard(mission_id, limit)
            snapshot["mission"] = await mission_settings.populate_application_name(snapshot["mission"])
            snapshot["ingestion"] = ingestion.snapshot(source_of(snapshot))
            references = settings.prediction_references.get(mission_id, {})
            # Una misión sin datum oficial aún puede planear desde un origen manual MSL.
            can_predict = settings.prediction_enabled
            next_allowed = (snapshot.get("predictionSettings") or {}).get("nextAllowedAt")
            if settings.prediction_enabled:
                snapshot["prediction"] = await repository.latest_prediction(mission_id)
                next_allowed = await repository.prediction_next_allowed_at(mission_id)
            can_command = (command_transport is not None and command_transport.supports(snapshot["mission"]) and
                           (mqtt_commands is None or source_of(snapshot) == settings.source))
            supported = list(mqtt_commands.profile.payload_hex) if mqtt_commands else [k for k in COMMAND_TYPES if k != "RELEASE_NOW"]
            if snapshot["mission"].get("telemetryProtocol") == "radiosonda-meca-v1":
                supported = ["PING", "RELEASE_NOW"]
            snapshot["permissions"] = {"canCommand": can_command, "canPredict": can_predict}
            snapshot["commandSettings"] = {"enabled": can_command, "supportedTypes": supported if can_command else [],
                "reason": None if can_command else "Pendiente de protocolo de comandos en firmware del dispositivo y perfil coincidente",
                "uplinkIntervalSeconds": 900 if snapshot["mission"].get("telemetryProtocol") == "radiosonda-meca-v1" else 21600}
            snapshot["csrfToken"] = csrf_token
            snapshot["predictionSettings"] = {"enabled": settings.prediction_enabled,
                "launchAltitudeReference": references.get("launchAltitudeReference", "unknown"),
                "gpsAltitudeReference": references.get("gpsAltitudeReference", "unknown"),
                "nextAllowedAt": (next_allowed.isoformat() if isinstance(next_allowed, datetime) else next_allowed)}
            return snapshot
        except MissionNotFound as exc:
            raise HTTPException(404, "Misión inexistente") from exc

    @app.get("/api/v1/missions/{mission_id}/packets", response_model=PacketPageDTO)
    async def packets(mission_id: str, cursor: Annotated[str | None, Query(max_length=512)] = None,
                      limit: Annotated[int, Query(ge=1, le=100)] = 50) -> dict:
        try:
            return await repository.packets(mission_id, cursor, limit)
        except MissionNotFound as exc:
            raise HTTPException(404, "Misión inexistente") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/v1/missions/{mission_id}/commands", response_model=CommandDTO, status_code=202)
    async def request_command(mission_id: str, payload: CommandRequest, request: Request) -> dict:
        token = request.headers.get("X-CSRF-Token", "")
        if (request.headers.get("Origin") not in settings.allowed_origins or
                not secrets.compare_digest(token.encode("utf-8"), csrf_token.encode("ascii"))):
            raise HTTPException(403, "Origen o token inválidos")
        if request.headers.get("Idempotency-Key") != str(payload.clientRequestId):
            raise HTTPException(422, "Idempotency-Key debe coincidir con clientRequestId")
        try:
            snapshot = await repository.dashboard(mission_id, 1)
            if payload.type == "RELEASE_NOW" and snapshot["mission"].get("telemetryProtocol") != "radiosonda-meca-v1":
                raise HTTPException(422, "El corte requiere un perfil de firmware compatible")
            if mqtt_commands is not None and source_of(snapshot) != settings.source:
                raise CommandUnavailable("El origen persistido de la misión no coincide con el perfil MQTT")
            if mqtt_commands is not None and payload.type not in mqtt_commands.profile.payload_hex:
                raise CommandUnavailable("Este comando no está definido en el perfil del firmware")
            return await commander.execute(snapshot["mission"], str(payload.clientRequestId), payload.type)
        except MissionNotFound as exc:
            raise HTTPException(404, "Misión inexistente") from exc
        except CommandConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except CommandUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc

    @app.put("/api/v1/missions/{mission_id}/parameters", response_model=MissionDTO)
    async def update_parameters(mission_id: str, payload: MissionParameters, request: Request) -> dict:
        token = request.headers.get("X-CSRF-Token", "")
        if (request.headers.get("Origin") not in settings.allowed_origins or
                not secrets.compare_digest(token.encode("utf-8"), csrf_token.encode("ascii"))):
            raise HTTPException(403, "Origen o token inválidos")
        try:
            mission = await mission_settings.update(mission_id, payload)
        except MissionNotFound as exc:
            raise HTTPException(404, "Misión inexistente") from exc
        except ConfigurationConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except (OSError, ValueError) as exc:
            raise HTTPException(503, "No se pudo guardar la configuración local de la misión") from exc
        hub.send(mission_id, {"type": "mission", "data": mission})
        return mission

    @app.post("/api/v1/missions/{mission_id}/predictions", response_model=PredictionDTO)
    async def predict(mission_id: str, payload: PredictionRequest, request: Request) -> dict:
        return await execute_prediction(mission_id, payload.model_dump(mode="json"), request)

    @app.get("/api/v1/demo/predictions", response_model=DemoPredictionSession)
    async def demo_session() -> dict:
        enabled = settings.demo_prediction_enabled
        next_allowed = await repository.prediction_next_allowed_at("satlink-demo") if enabled else None
        return {"enabled": enabled, "csrfToken": csrf_token if enabled else None,
                "nextAllowedAt": next_allowed.isoformat() if next_allowed else None,
                "prediction": await repository.latest_prediction("satlink-demo") if enabled else None,
                "predictionHistory": await repository.prediction_history("satlink-demo") if enabled else []}

    @app.post("/api/v1/demo/predictions", response_model=PredictionDTO)
    async def demo_predict(payload: DemoPredictionRequest, request: Request) -> dict:
        return await execute_prediction("satlink-demo", payload.parameters.model_dump(mode="json"), request,
            simulated={"phase": payload.phase, "sample": payload.sample.model_dump(mode="json") if payload.sample else None})

    async def execute_prediction(mission_id: str, parameters: dict, request: Request,
                                 simulated: dict | None = None) -> dict:
        token = request.headers.get("X-CSRF-Token", "")
        enabled = settings.demo_prediction_enabled if simulated is not None else settings.prediction_enabled
        if (not enabled or predictor is None or
                request.headers.get("Origin") not in settings.allowed_origins or
                not secrets.compare_digest(token.encode("utf-8"), csrf_token.encode("ascii"))):
            raise HTTPException(403, "Predicción no habilitada, origen o token inválidos")
        try:
            references = ({"launchAltitudeReference": "MSL", "gpsAltitudeReference": "MSL"}
                          if simulated is not None else settings.prediction_references.get(mission_id, {}))
            if simulated is None:
                return await predictor.execute(mission_id, parameters, references)
            return await predictor.execute(mission_id, parameters, references, simulated=simulated)
        except MissionNotFound as exc:
            raise HTTPException(404, "Misión inexistente") from exc
        except PredictionInvalid as exc:
            raise HTTPException(422, str(exc)) from exc
        except PredictionCooldown as exc:
            seconds = max(1, math.ceil((exc.next_allowed_at - datetime.now(timezone.utc)).total_seconds()))
            raise HTTPException(429, str(exc), headers={"Retry-After": str(seconds),
                "X-Prediction-Next-Allowed-At": exc.next_allowed_at.isoformat()}) from exc
        except PredictionTimeout as exc:
            raise HTTPException(504, str(exc)) from exc
        except PredictionUnavailable as exc:
            raise HTTPException(502, str(exc)) from exc

    @app.get("/api/v1/missions/{mission_id}/telemetry", response_model=HistoryDTO)
    async def history(mission_id: str, from_: Annotated[str | None, Query(alias="from")] = None,
                      to: str | None = None, cursor: Annotated[str | None, Query(max_length=2048)] = None,
                      limit: Annotated[int, Query(ge=1, le=1200)] = 200) -> dict:
        try:
            return await repository.history(mission_id, utc_time(from_) if from_ is not None else None,
                utc_time(to) if to is not None else None, cursor, limit)
        except MissionNotFound as exc:
            raise HTTPException(404, "Misión inexistente") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/v1/missions/{mission_id}/telemetry/window", response_model=WindowDTO)
    async def window(mission_id: str, from_: Annotated[str | None, Query(alias="from")] = None,
                     to: str | None = None) -> dict:
        try:
            return await queries.window(mission_id, utc_time(from_) if from_ is not None else None,
                                        utc_time(to) if to is not None else None)
        except MissionNotFound as exc:
            raise HTTPException(404, "Misión inexistente") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/v1/missions/{mission_id}/telemetry/export.csv", response_class=StreamingResponse,
             responses={200: {"content": {"text/csv": {"schema": {"type": "string"}}}}})
    async def export_csv(mission_id: str, from_: Annotated[str | None, Query(alias="from")] = None,
                         to: str | None = None) -> CsvStreamingResponse:
        try:
            export = await queries.export(mission_id, utc_time(from_) if from_ is not None else None,
                                          utc_time(to) if to is not None else None)
            return CsvStreamingResponse(export)
        except MissionNotFound as exc:
            raise HTTPException(404, "Misión inexistente") from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.websocket("/api/v1/missions/{mission_id}/stream")
    async def stream(websocket: WebSocket, mission_id: str) -> None:
        try:
            snapshot = await repository.dashboard(mission_id, 1)
        except MissionNotFound:
            await websocket.close(code=1008)
            return
        source = source_of(snapshot)
        with subscription(mission_id, source) as queue:
            await websocket.accept()
            await websocket.send_json({"type": "ingestion", "data": ingestion.snapshot(source)})
            async def sending() -> None:
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=20)
                    except TimeoutError:
                        message = {"type": "heartbeat"}
                    if message is None:
                        await websocket.close(code=1013)
                        return
                    await websocket.send_json(message)
            async def receiving() -> None:
                while True:
                    event = await websocket.receive()
                    if event["type"] == "websocket.disconnect":
                        return
            tasks = {asyncio.create_task(sending()), asyncio.create_task(receiving())}
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    with suppress(WebSocketDisconnect):
                        task.result()
            except asyncio.CancelledError:
                # El servidor también puede cancelar al cerrar una conexión.
                pass
            finally:
                for task in tasks:
                    task.cancel()
                with suppress(asyncio.CancelledError):
                    await asyncio.gather(*tasks, return_exceptions=True)

    return app
