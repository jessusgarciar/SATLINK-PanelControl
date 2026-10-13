from typing import Protocol
from datetime import datetime
from collections.abc import AsyncIterator
from app.domain.entities.telemetry import IncomingUplink, JsonObject, Mission


class UplinkDecoder(Protocol):
    def decode(self, topic: str, payload: bytes, source: str) -> IncomingUplink: ...


class TelemetryStore(Protocol):
    async def find_mission(self, source: str, application_id: str, dev_eui: str) -> Mission | None: ...
    async def persist(self, mission: Mission, event: IncomingUplink, telemetry: JsonObject) -> bool:
        """Return True only for a new event, after the transaction has committed."""
        ...
    async def reject(self, source: str, topic: str, payload: bytes, reason: str) -> None: ...


class TelemetryPublisher(Protocol):
    async def publish(self, mission_id: str, telemetry: JsonObject) -> None: ...


class IngestionPublisher(Protocol):
    async def publish_ingestion(self, data: JsonObject, mission_ids: set[str] | None = None) -> None: ...


class TelemetryExport(Protocol):
    def __aiter__(self) -> AsyncIterator[JsonObject]: ...
    async def aclose(self) -> None: ...


class TelemetryQueries(Protocol):
    async def dashboard(self, mission_id: str, limit: int = 1200) -> JsonObject: ...
    async def history(self, mission_id: str, from_time: datetime | None = None,
                      to_time: datetime | None = None, cursor: str | None = None,
                      limit: int = 200) -> JsonObject: ...
    async def window(self, mission_id: str, from_time: datetime | None,
                     to_time: datetime) -> JsonObject: ...
    async def export(self, mission_id: str, from_time: datetime | None,
                     to_time: datetime) -> TelemetryExport: ...
