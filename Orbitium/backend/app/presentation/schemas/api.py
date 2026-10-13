from typing import Annotated, Literal
from pydantic import Field, field_validator
from app.presentation.schemas.uplink import utc_time
from app.presentation.schemas.base import DTO, Position
from app.presentation.schemas.prediction import PredictionDTO, PredictionSettingsDTO


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
    device: "DeviceDTO | None" = None
    radio: "RadioDTO | None" = None

    @field_validator("receivedAt")
    @classmethod
    def timestamp(cls, value: str) -> str:
        utc_time(value)
        return value


class DeviceDTO(DTO):
    gpsActive: bool | None
    gpsFix: bool | None
    satellites: Annotated[int, Field(ge=0, le=255)] | None
    batteryPct: Annotated[int, Field(ge=0, le=100)] | None
    charging: bool | None
    usbPowered: bool | None


class RadioDTO(DTO):
    gatewayId: str | None
    frequencyHz: Annotated[int, Field(gt=0)] | None
    dataRate: Annotated[int, Field(ge=0, le=15)] | None
    fPort: Annotated[int, Field(ge=1, le=255)] | None


class IngestionDTO(DTO):
    source: str
    status: Literal["disabled", "connecting", "connected", "reconnecting", "offline"]
    updatedAt: str

    @field_validator("updatedAt")
    @classmethod
    def timestamp(cls, value: str) -> str:
        utc_time(value)
        return value


class Permissions(DTO):
    canCommand: Literal[False] = False
    canPredict: bool = False


class DashboardDTO(DTO):
    mission: MissionDTO
    telemetry: list[TelemetryDTO]
    commands: Annotated[list, Field(max_length=0)] = Field(default_factory=list)
    events: Annotated[list, Field(max_length=0)] = Field(default_factory=list)
    prediction: "PredictionDTO | None" = None
    permissions: Permissions = Field(default_factory=Permissions)
    csrfToken: str | None = None
    ingestion: IngestionDTO | None = None
    predictionSettings: "PredictionSettingsDTO" = Field(default_factory=lambda: PredictionSettingsDTO())


class HistoryDTO(DTO):
    items: list[TelemetryDTO]
    nextCursor: str | None


class WindowDTO(DTO):
    from_: str | None = Field(alias="from")
    to: str
    total: Annotated[int, Field(ge=0)]
    series: Annotated[list[TelemetryDTO], Field(max_length=600)]
    track: Annotated[list[TelemetryDTO], Field(max_length=500)]
