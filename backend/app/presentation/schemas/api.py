from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.presentation.schemas.uplink import utc_time


class DTO(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)


class Position(DTO):
    latitude: Annotated[float, Field(ge=-90, le=90)]
    longitude: Annotated[float, Field(ge=-180, le=180)]
    altitudeM: Annotated[float, Field(ge=-500, le=65534)]


class MissionConfig(DTO):
    id: Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,128}$")]
    name: Annotated[str, Field(min_length=1, max_length=256)]
    source: Annotated[str, Field(min_length=1, max_length=128)]
    applicationId: Annotated[str, Field(min_length=1, max_length=128, pattern=r"^[^/+#]+$")]
    deviceEui: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{16}$")]
    launch: Position
    launchLabel: Annotated[str, Field(min_length=1, max_length=256)]
    targetRelativeAltitudeM: Annotated[float, Field(ge=1000, le=15000)] = 15000
    nominalAscentMs: Annotated[float, Field(ge=1, le=10)]
    nominalDescentMs: Annotated[float, Field(ge=1, le=15)]
    watchdogSeconds: Annotated[int, Field(ge=1, le=86400)]
    staleAfterSeconds: Annotated[int, Field(ge=1, le=3600)]
    region: Literal["US915"] = "US915"

    @field_validator("deviceEui")
    @classmethod
    def lower_eui(cls, value: str) -> str:
        return value.lower()


class MissionDTO(DTO):
    id: str
    name: str
    updatedAt: str
    startedAt: str | None
    endedAt: str | None
    phase: Literal["unknown"]
    launch: Position
    launchLabel: str
    targetRelativeAltitudeM: Annotated[float, Field(ge=1000, le=15000)]
    nominalAscentMs: float
    nominalDescentMs: float
    watchdogSeconds: int
    staleAfterSeconds: int
    deviceEui: str
    region: str
    beaconOn: None


class TelemetryDTO(DTO):
    id: str
    missionId: str
    receivedAt: str
    frameCounter: Annotated[int, Field(ge=0, le=4294967295)]
    latitude: Annotated[float, Field(ge=-90, le=90)] | None
    longitude: Annotated[float, Field(ge=-180, le=180)] | None
    altitudeGpsM: Annotated[float, Field(ge=-500, le=32767)] | None
    relativeAltitudeM: float | None
    altitudeBarometricM: None
    verticalSpeedMs: None
    temperatureC: Annotated[float, Field(ge=-127, le=127)] | None
    pressureHpa: Annotated[float, Field(ge=5, le=1270)] | None
    humidityPct: None
    batteryV: Annotated[float, Field(ge=0, le=5.08)] | None
    rssiDbm: Annotated[float, Field(ge=-200, le=20)] | None
    snrDb: Annotated[float, Field(ge=-40, le=40)] | None

    @field_validator("receivedAt")
    @classmethod
    def timestamp(cls, value: str) -> str:
        utc_time(value)
        return value


class Permissions(DTO):
    canCommand: Literal[False] = False
    canPredict: Literal[False] = False


class DashboardDTO(DTO):
    mission: MissionDTO
    telemetry: list[TelemetryDTO]
    commands: Annotated[list, Field(max_length=0)] = Field(default_factory=list)
    events: Annotated[list, Field(max_length=0)] = Field(default_factory=list)
    prediction: None = None
    permissions: Permissions = Field(default_factory=Permissions)
    csrfToken: None = None


class HistoryDTO(DTO):
    items: list[TelemetryDTO]
    nextCursor: str | None
