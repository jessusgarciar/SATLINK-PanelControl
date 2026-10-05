import asyncio
import secrets
import math
from datetime import datetime, timezone
from contextlib import asynccontextmanager, contextmanager, suppress
from typing import Annotated, AsyncIterator, Iterator
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from app.application.use_cases.ingest import IngestTelemetry
from app.application.use_cases.ingestion_state import IngestionState
from app.application.use_cases.query_telemetry import QueryTelemetry
from app.bootstrap.config import Settings
from app.domain.entities.telemetry import MissionNotFound
from app.domain.entities.telemetry import JsonObject
from app.infrastructure.database.store import PostgresStore
from app.infrastructure.mqtt.consumer import consume
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.api.local import LocalOnlyMiddleware
from app.presentation.api.streaming import CsvStreamingResponse
from app.presentation.schemas.api import DashboardDTO, HistoryDTO, WindowDTO
from app.presentation.schemas.uplink import ChirpStackDecoder, utc_time
from app.presentation.websocket.hub import TelemetryHub
from app.application.ports.prediction import PredictionProvider
from app.application.use_cases.predict import PredictMission
from app.domain.entities.prediction import PredictionCooldown, PredictionInvalid, PredictionTimeout, PredictionUnavailable
from app.infrastructure.prediction.tawhiri import TawhiriProvider
from app.presentation.schemas.prediction import PredictionDTO, PredictionRequest


def create_app(settings: Settings, store: PostgresStore | None = None,
               publisher: TelemetryHub | None = None, *,
               prediction_provider: PredictionProvider | None = None) -> FastAPI:
    repository = store if store is not None else PostgresStore(settings.database_url)
    hub = publisher if publisher is not None else TelemetryHub()
    ingestor = IngestTelemetry(repository, hub, settings.source, ChirpStackDecoder(decode_payload))
    ingestion = IngestionState(settings.source, settings.mqtt_enabled, hub)
    queries = QueryTelemetry(repository)
    provider = prediction_provider
    if provider is None and settings.prediction_enabled:
        provider = TawhiriProvider(settings.prediction_url)
    predictor = None if provider is None else PredictMission(repository, provider, hub)
    csrf_token = secrets.token_urlsafe(32)

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
        if settings.mqtt_enabled:
            task = asyncio.create_task(consume(settings.mqtt_host, settings.mqtt_port,
                settings.mqtt_username, settings.mqtt_password, settings.mqtt_tls,
                settings.mqtt_client_id, ingestor.execute, ingestion.update))
        try:
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

    @app.get("/api/v1/missions/{mission_id}/dashboard", response_model=DashboardDTO)
    async def dashboard(mission_id: str, limit: Annotated[int, Query(ge=1, le=1200)] = 1200) -> dict:
        try:
            snapshot = await repository.dashboard(mission_id, limit)
            snapshot["ingestion"] = ingestion.snapshot(source_of(snapshot))
            references = settings.prediction_references.get(mission_id, {})
            can_predict = settings.prediction_enabled and references.get("launchAltitudeReference") == "MSL"
            next_allowed = (snapshot.get("predictionSettings") or {}).get("nextAllowedAt")
            if settings.prediction_enabled:
                snapshot["prediction"] = await repository.latest_prediction(mission_id)
                next_allowed = await repository.prediction_next_allowed_at(mission_id)
            snapshot["permissions"] = {"canCommand": False, "canPredict": can_predict}
            snapshot["csrfToken"] = csrf_token if can_predict else None
            snapshot["predictionSettings"] = {"enabled": settings.prediction_enabled,
                "launchAltitudeReference": references.get("launchAltitudeReference", "unknown"),
                "gpsAltitudeReference": references.get("gpsAltitudeReference", "unknown"),
                "nextAllowedAt": (next_allowed.isoformat() if isinstance(next_allowed, datetime) else next_allowed)}
            return snapshot
        except MissionNotFound as exc:
            raise HTTPException(404, "Misión inexistente") from exc

    @app.post("/api/v1/missions/{mission_id}/predictions", response_model=PredictionDTO)
    async def predict(mission_id: str, payload: PredictionRequest, request: Request) -> dict:
        token = request.headers.get("X-CSRF-Token", "")
        if (not settings.prediction_enabled or predictor is None or
                request.headers.get("Origin") not in settings.allowed_origins or
                not secrets.compare_digest(token.encode("utf-8"), csrf_token.encode("ascii"))):
            raise HTTPException(403, "Predicción no habilitada, origen o token inválidos")
        try:
            return await predictor.execute(mission_id, payload.model_dump(mode="json"),
                                           settings.prediction_references.get(mission_id, {}))
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
