import asyncio
from contextlib import asynccontextmanager, suppress
from typing import Annotated, AsyncIterator
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from app.application.use_cases.ingest import IngestTelemetry
from app.bootstrap.config import Settings
from app.domain.entities.telemetry import MissionNotFound
from app.infrastructure.database.store import PostgresStore
from app.infrastructure.mqtt.consumer import consume
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.api.local import LocalOnlyMiddleware
from app.presentation.schemas.api import DashboardDTO, HistoryDTO
from app.presentation.schemas.uplink import ChirpStackDecoder, utc_time
from app.presentation.websocket.hub import TelemetryHub


def create_app(settings: Settings, store: PostgresStore | None = None,
               publisher: TelemetryHub | None = None) -> FastAPI:
    repository = store if store is not None else PostgresStore(settings.database_url)
    hub = publisher if publisher is not None else TelemetryHub()
    ingestor = IngestTelemetry(repository, hub, settings.source, ChirpStackDecoder(decode_payload))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        task = None
        if settings.mqtt_enabled:
            task = asyncio.create_task(consume(settings.mqtt_host, settings.mqtt_port,
                settings.mqtt_username, settings.mqtt_password, settings.mqtt_tls,
                settings.mqtt_client_id, ingestor.execute))
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            await repository.close()

    app = FastAPI(title="SATLINK · Telemetría local", version="1.0.0", lifespan=lifespan)
    app.add_middleware(LocalOnlyMiddleware, allowed_origins=settings.allowed_origins)
    app.state.ingestor, app.state.store, app.state.hub = ingestor, repository, hub

    @app.get("/api/v1/missions/{mission_id}/dashboard", response_model=DashboardDTO)
    async def dashboard(mission_id: str, limit: Annotated[int, Query(ge=1, le=1200)] = 1200) -> dict:
        try:
            return await repository.dashboard(mission_id, limit)
        except MissionNotFound as exc:
            raise HTTPException(404, "Misión inexistente") from exc

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

    @app.websocket("/api/v1/missions/{mission_id}/stream")
    async def stream(websocket: WebSocket, mission_id: str) -> None:
        try:
            await repository.dashboard(mission_id, 1)
        except MissionNotFound:
            await websocket.close(code=1008)
            return
        with hub.subscribe(mission_id) as queue:
            await websocket.accept()
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
