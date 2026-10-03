import base64
import binascii
import json
import math
import re
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from app.domain.entities.telemetry import IncomingUplink, JsonObject

RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def utc_time(value: str) -> datetime:
    if not isinstance(value, str) or not RFC3339.fullmatch(value):
        raise ValueError("Fecha RFC3339 con zona horaria requerida")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


class DeviceInfo(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")
    applicationId: Annotated[str, Field(min_length=1, max_length=128)]
    devEui: Annotated[str, Field(pattern=r"^[0-9a-fA-F]{16}$")]


class UplinkEnvelope(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", allow_inf_nan=False)
    deduplicationId: str
    time: str
    deviceInfo: DeviceInfo
    # Protobuf JSON omite campos escalares cuyo valor es cero.
    fCnt: Annotated[int, Field(ge=0, le=4294967295)] = 0
    fPort: Annotated[int, Field(ge=1, le=255)]
    data: str
    rxInfo: list[dict[str, Any]] = Field(default_factory=list, max_length=256)

    @field_validator("deduplicationId")
    @classmethod
    def event_id(cls, value: str) -> str:
        return str(UUID(value))

    @field_validator("time")
    @classmethod
    def event_time(cls, value: str) -> str:
        utc_time(value)
        return value


def reject_constant(value: str) -> None:
    raise ValueError("Constante JSON no válida")


def finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Número JSON no finito")
    return result


def json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Clave JSON duplicada")
        result[key] = value
    return result


def validate_json_strings(value: Any) -> None:
    # JSONB no admite NUL ni sustitutos Unicode sin pareja.
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("Texto JSON con NUL")
        value.encode("utf-8")
    elif isinstance(value, dict):
        for key, child in value.items():
            validate_json_strings(key)
            validate_json_strings(child)
    elif isinstance(value, list):
        for child in value:
            validate_json_strings(child)


def radio_value(value: Any, lower: float, upper: float) -> float | None:
    return float(value) if type(value) in (int, float) and math.isfinite(value) and lower <= value <= upper else None


class ChirpStackDecoder:
    def __init__(self, codec: Callable[[bytes, int], JsonObject]) -> None:
        self.codec = codec

    def decode(self, topic: str, payload: bytes, source: str) -> IncomingUplink:
        if len(payload) > 262144:
            raise ValueError("Evento MQTT demasiado grande")
        try:
            raw = json.loads(payload, parse_constant=reject_constant, parse_float=finite_float,
                             object_pairs_hook=json_object)
            validate_json_strings(raw)
            envelope = UplinkEnvelope.model_validate(raw)
            expected = f"application/{envelope.deviceInfo.applicationId}/device/{envelope.deviceInfo.devEui}/event/up"
            if topic != expected:
                raise ValueError("El topic y el dispositivo/aplicación del evento no coinciden")
            binary = base64.b64decode(envelope.data, validate=True)
            decoded = self.codec(binary, envelope.fPort)
        except (ValidationError, binascii.Error, UnicodeError, TypeError, RecursionError) as exc:
            raise ValueError("Evento ChirpStack inválido") from exc
        metadata = decoded.pop("metadata")
        # RSSI y SNR siempre pertenecen al mismo gateway; preferir SNR, luego RSSI.
        receptions = [(radio_value(r.get("snr"), -40, 40), radio_value(r.get("rssi"), -200, 20),
                       str(r.get("gatewayId", ""))) for r in envelope.rxInfo]
        best = max(receptions, key=lambda r: (r[0] if r[0] is not None else -math.inf,
                                              r[1] if r[1] is not None else -math.inf, r[2]),
                   default=(None, None, ""))
        decoded.update(snrDb=best[0], rssiDbm=best[1])
        metadata["selectedGatewayId"] = best[2] or None
        return IncomingUplink(source, envelope.deviceInfo.applicationId,
                              envelope.deviceInfo.devEui.lower(), envelope.deduplicationId,
                              utc_time(envelope.time), envelope.fCnt, payload, raw, decoded, metadata)
