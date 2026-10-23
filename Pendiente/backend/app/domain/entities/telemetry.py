"""Entidades de ingestión independientes de transporte y base de datos."""
from dataclasses import dataclass
from datetime import datetime
from typing import Any

JsonObject = dict[str, Any]


def observed_application_name(event: JsonObject) -> str | None:
    info = event.get("deviceInfo")
    value = info.get("applicationName") if isinstance(info, dict) else None
    return value.strip() if isinstance(value, str) and 1 <= len(value.strip()) <= 256 else None


@dataclass(frozen=True)
class IncomingUplink:
    source: str
    application_id: str
    dev_eui: str
    deduplication_id: str
    received_at: datetime
    frame_counter: int
    raw_payload: bytes
    raw_event: JsonObject
    measurements: JsonObject
    metadata: JsonObject


@dataclass(frozen=True)
class Mission:
    id: str
    source: str
    application_id: str
    dev_eui: str
    snapshot: JsonObject


class MissionNotFound(LookupError):
    pass


class ConfigurationConflict(ValueError):
    pass
