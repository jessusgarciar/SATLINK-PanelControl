"""Perfil fijo de telemetría del Ejercicio 09. Aviso MIT en THIRD_PARTY_NOTICES.md."""
import struct
from app.domain.entities.telemetry import JsonObject

CODEC_VERSION = "picaro-full-19-v1"


def bounded(value: float, lower: float, upper: float) -> float | None:
    return value if lower <= value <= upper else None


def decode_payload(payload: bytes, fport: int) -> JsonObject:
    # Se agregó esta validación porque en el Ejercicio 09 el payload contiene 19 bytes.
    if isinstance(fport, bool) or fport != 10 or len(payload) != 19:
        raise ValueError("PICARO FULL requiere fPort 10 y exactamente 19 bytes")
    status, lat, lon, altitude, sats, mv, pct, temp, pressure = struct.unpack(
        ">BiihBHBhH", payload
    )
    latitude = bounded(lat / 1_000_000, -90, 90)
    longitude = bounded(lon / 1_000_000, -180, 180)
    valid = bool(status & 1) and latitude is not None and longitude is not None
    return {
        "latitude": latitude if valid else None,
        "longitude": longitude if valid else None,
        "altitudeGpsM": bounded(altitude, -500, 32767) if valid else None,
        "temperatureC": bounded(temp / 100, -127, 127),
        "pressureHpa": bounded(pressure / 10, 5, 1270),
        "batteryV": bounded(mv / 1000, 0, 5.08),
        "humidityPct": None,
        "metadata": {
            "codecVersion": CODEC_VERSION, "status": status, "gpsFix": bool(status & 1),
            "gpsActive": bool(status & 32), "charging": bool(status & 2),
            "usbPowered": bool(status & 4), "imuOk": bool(status & 8),
            "magOk": bool(status & 16), "satellites": sats,
            "batteryPct": pct if pct <= 100 else None,
        },
    }
