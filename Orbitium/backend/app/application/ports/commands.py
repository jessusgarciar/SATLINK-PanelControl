from datetime import datetime
from typing import Protocol
from app.domain.entities.telemetry import JsonObject


class CommandStore(Protocol):
    async def reserve_command(self, mission_id: str, request_id: str, kind: str,
                              now: datetime) -> tuple[JsonObject, bool]: ...
    async def command_evidence(self, mission_id: str, command_id: str, status: str,
                               evidence: str, *, started_at: datetime | None = None) -> tuple[JsonObject, JsonObject | None]: ...


class CommandTransport(Protocol):
    def supports(self, mission: JsonObject) -> bool: ...
    async def send(self, mission: JsonObject, command: JsonObject) -> None: ...


class CommandPublisher(Protocol):
    def send(self, mission_id: str, message: JsonObject) -> None: ...
