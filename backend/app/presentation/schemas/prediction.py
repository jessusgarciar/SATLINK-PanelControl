from typing import Annotated, Literal
from pydantic import Field, field_validator
from app.presentation.schemas.base import DTO, Position
from app.presentation.schemas.uplink import utc_time


class PredictionNumbers(DTO):
    targetRelativeAltitudeM: Annotated[float, Field(ge=1000, le=15000)]
    ascentRateMs: Annotated[float, Field(ge=1, le=10)]
    descentRateMs: Annotated[float, Field(ge=1, le=15)]


class PlannedPredictionRequest(PredictionNumbers):
    mode: Literal["planned"]
    launchDatetime: str

    @field_validator("launchDatetime")
    @classmethod
    def timestamp(cls, value: str) -> str:
        utc_time(value)
        return value


class AscendingPredictionRequest(PredictionNumbers):
    mode: Literal["ascending"]


PredictionRequest = Annotated[PlannedPredictionRequest | AscendingPredictionRequest,
                              Field(discriminator="mode")]


class TimedPosition(Position):
    time: str

    @field_validator("time")
    @classmethod
    def timestamp(cls, value: str) -> str:
        utc_time(value)
        return value


class PredictionContextDTO(DTO):
    mode: Literal["planned", "ascending"]
    origin: Position
    originAt: str
    telemetryId: str | None
    dataset: str | None
    altitudeReference: Literal["MSL"]

    @field_validator("originAt")
    @classmethod
    def timestamp(cls, value: str) -> str:
        utc_time(value)
        return value


class PredictionDTO(DTO):
    id: str
    missionId: str
    generatedAt: str
    weatherAt: str | None
    source: Literal["tawhiri"]
    parameters: PredictionRequest
    context: PredictionContextDTO
    trajectory: Annotated[list[TimedPosition], Field(min_length=2, max_length=10000)]
    release: TimedPosition
    landing: TimedPosition

    @field_validator("generatedAt", "weatherAt")
    @classmethod
    def timestamp(cls, value: str | None) -> str | None:
        if value is not None:
            utc_time(value)
        return value


class PredictionSettingsDTO(DTO):
    enabled: bool = False
    launchAltitudeReference: Literal["MSL", "unknown"] = "unknown"
    gpsAltitudeReference: Literal["MSL", "unknown"] = "unknown"
    nextAllowedAt: str | None = None
