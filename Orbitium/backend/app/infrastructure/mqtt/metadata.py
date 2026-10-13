"""Metadatos observados de ChirpStack, también para muestras históricas."""
import math
from typing import Any
from app.domain.entities.telemetry import JsonObject


def number(value: Any, lower: float, upper: float) -> float | None:
    return float(value) if type(value) in (int, float) and math.isfinite(value) and lower <= value <= upper else None


def integer(value: Any, lower: int, upper: int) -> int | None:
    return value if type(value) is int and lower <= value <= upper else None


def metadata_groups(codec: JsonObject, event: JsonObject) -> tuple[JsonObject | None, JsonObject | None]:
    device = None
    if codec:
        device = {name: codec.get(name) if type(codec.get(name)) is bool else None
                  for name in ("gpsActive", "gpsFix", "charging", "usbPowered")}
        device["satellites"] = integer(codec.get("satellites"), 0, 255)
        device["batteryPct"] = integer(codec.get("batteryPct"), 0, 100)
    radio = None
    if event:
        receptions = event.get("rxInfo", [])
        receptions = receptions if isinstance(receptions, list) else []
        valid = [r for r in receptions if isinstance(r, dict)]
        best = max(valid, key=lambda r: (
            number(r.get("snr"), -40, 40) if number(r.get("snr"), -40, 40) is not None else -math.inf,
            number(r.get("rssi"), -200, 20) if number(r.get("rssi"), -200, 20) is not None else -math.inf,
            r.get("gatewayId") if isinstance(r.get("gatewayId"), str) else ""), default={})
        gateway = codec.get("selectedGatewayId") or best.get("gatewayId")
        tx = event.get("txInfo")
        tx = tx if isinstance(tx, dict) else {}
        # Se agregó esta información ya que en el Ejercicio 10 se muestran frecuencia y DR.
        radio = {"gatewayId": gateway if isinstance(gateway, str) and gateway else None,
                 "frequencyHz": integer(tx.get("frequency"), 1, 2**63 - 1),
                 "dataRate": integer(event.get("dr"), 0, 15),
                 "fPort": integer(event.get("fPort"), 1, 255)}
    return device, radio


def enrich_telemetry(data: JsonObject, details: JsonObject | None) -> JsonObject:
    details = details if isinstance(details, dict) else {}
    codec = details.get("codec")
    event = details.get("event")
    device, radio = metadata_groups(codec if isinstance(codec, dict) else {},
                                    event if isinstance(event, dict) else {})
    return {**data, "device": data.get("device") or device, "radio": data.get("radio") or radio}
