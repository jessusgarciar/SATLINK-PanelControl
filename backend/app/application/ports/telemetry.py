from typing import Protocol
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
