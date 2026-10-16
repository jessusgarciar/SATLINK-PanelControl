"""VUELO D-64, fPort 17: tres paquetes de 11 bytes, little-endian.

Adaptado del codec observado en el perfil Radiosonda-Terreno-ClaseA.
Cada evento conserva solo sus medidas; no se rellenan con otra ráfaga.
"""
import struct
from app.domain.entities.telemetry import JsonObject

CODEC_VERSION = "picaro-vuelo-11-v1"


def bounded(value: float, lower: float, upper: float) -> float | None:
    return value if lower <= value <= upper else None


def available(value: int, sentinel: int, scale: float = 1) -> float | None:
    return None if value == sentinel else value / scale


def decode_vuelo(payload: bytes) -> JsonObject:
    if len(payload) != 11:
        raise ValueError("VUELO requiere exactamente 11 bytes en fPort 17")
    kind = payload[0] >> 6
    if kind not in (1, 2, 3):
        raise ValueError("Tipo de paquete VUELO desconocido")
    metadata = {"codecVersion": CODEC_VERSION, "packetType": kind,
                "burst": payload[0] & 63}
    result = dict.fromkeys(("latitude", "longitude", "altitudeGpsM", "temperatureC",
                            "humidityPct", "pressureHpa", "batteryV", "verticalSpeedMs"))
    result["metadata"] = metadata
    if kind == 1:
        lat, lon, altitude = struct.unpack_from("<iiH", payload, 1)
        latitude = bounded(lat / 10_000_000, -90, 90)
        longitude = bounded(lon / 10_000_000, -180, 180)
        fix = (lat != 0 or lon != 0) and latitude is not None and longitude is not None
        metadata["gpsFix"] = fix
        if fix:
            result.update(latitude=latitude, longitude=longitude,
                          altitudeGpsM=available(altitude, 65535))
    elif kind == 2:
        temp, pressure, humidity, mv, pct, sats, flags = struct.unpack_from("<hHBHBBB", payload, 1)
        result.update(
            temperatureC=None if temp == 32767 else bounded(temp / 100, -127, 127),
            pressureHpa=None if pressure == 65535 else bounded(pressure / 10, 5, 1270),
            humidityPct=None if humidity == 255 else bounded(humidity, 0, 100),
            batteryV=bounded(mv / 1000, 0, 5.08))
        metadata.update(gpsFix=bool(flags & 1), usbPowered=bool(flags & 2),
                        charging=bool(flags & 4), gpsActive=bool(flags & 8),
                        magOk=bool(flags & 16), bmeOk=bool(flags & 32),
                        satellites=None if sats == 255 else sats,
                        batteryPct=pct if pct <= 100 else None)
    else:
        speed, heading, hdop, vertical = struct.unpack_from("<HHBh", payload, 1)
        result["verticalSpeedMs"] = None if vertical == 32767 else bounded(vertical / 10, -200, 200)
        metadata.update(speedKmh=available(speed, 65535, 10),
                        headingDeg=available(heading, 65535, 10),
                        hdop=available(hdop, 255, 10),
                        uptimeSeconds=int.from_bytes(payload[8:11], "little"))
    return result
