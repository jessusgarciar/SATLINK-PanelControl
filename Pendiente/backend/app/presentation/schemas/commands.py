from uuid import UUID
from pydantic import Field
from typing import Annotated, Literal
from app.domain.entities.commands import CommandType
from app.presentation.schemas.base import DTO


class CommandRequest(DTO):
    type: CommandType
    clientRequestId: Annotated[UUID, Field(strict=False)]


class CommandDTO(DTO):
    id: str
    missionId: str
    clientRequestId: str
    type: CommandType
    status: Literal["pending", "sent", "received", "executed", "rejected", "expired"]
    createdAt: str
    updatedAt: str
    evidence: str
    watchdogSeconds: int
    simulated: Literal[False] = False


class CommandSettingsDTO(DTO):
    enabled: bool = False
    supportedTypes: list[CommandType] = Field(default_factory=list)
    reason: str | None = "Pendiente de protocolo de comandos en el firmware Heltec"
    uplinkIntervalSeconds: Annotated[int, Field(ge=1)] = 21600
