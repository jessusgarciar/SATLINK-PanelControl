"""Contrato Heltec/T-Beam radiosonda v1; cada resultado contiene solo su paquete."""
import struct
from app.domain.entities.telemetry import JsonObject

PORT_TYPES = {20: "posicion", 21: "atmosfera", 22: "ambiente", 23: "interno", 30: "polo", 31: "corte"}


def decode_radiosonda(payload: bytes, fport: int) -> JsonObject:
    if fport not in PORT_TYPES or len(payload) != (4 if fport == 30 else 11):
        raise ValueError("Radiosonda: puerto o longitud inválidos")
    def value(fmt: str, offset: int, sentinel: int, scale: float = 1) -> float | None:
        raw = struct.unpack_from("<" + fmt, payload, offset)[0]
        return None if raw == sentinel else raw / scale
    fields: JsonObject = {}
    meta: JsonObject = {"codecVersion": "radiosonda-v1", "packetType": PORT_TYPES[fport], "fPort": fport}
    if fport == 20:
        lat, lon, alt, sats = struct.unpack("<iiHB", payload)
        valid = not (lat == lon == 0) and alt != 65535
        if valid and not (-90 <= lat / 1e7 <= 90 and -180 <= lon / 1e7 <= 180):
            raise ValueError("Radiosonda: coordenadas fuera de rango")
        fields.update(latitude=lat / 1e7 if valid else None, longitude=lon / 1e7 if valid else None,
                      altitudeGpsM=alt if valid else None)
        meta.update(gpsFix=valid, satellites=None if sats == 255 else sats)
    elif fport == 21:
        fields.update(temperatureC=value("h", 0, 32767, 100), pressureHpa=value("H", 2, 65535, 10),
                      humidityPct=value("B", 4, 255))
        meta.update(tvocPpb=value("H", 5, 65535), eco2Ppm=value("H", 7, 65535),
                    aqi=value("B", 9, 255), batteryPct=None if payload[10] == 255 else payload[10])
    elif fport == 22:
        fields["batteryV"] = value("H", 7, 65535, 1000)
        lux = struct.unpack_from("<H", payload, 3)[0]
        meta.update(ahtTemperatureC=value("h", 0, 32767, 100), ahtHumidityPct=value("B", 2, 255),
                    lightLux=None if lux in (65534, 65535) else lux, lightSaturated=lux == 65534,
                    dhtTemperatureC=value("b", 5, 127), dhtHumidityPct=value("B", 6, 255),
                    uptimeS=struct.unpack_from("<H", payload, 9)[0] * 4)
    elif fport == 23:
        # El sensor principal Heltec está en 21; los de placa no lo sustituyen.
        flags = payload[10]
        meta.update(boardTemperatureC=value("h", 0, 32767, 100), boardPressureHpa=value("H", 2, 65535, 10),
                    boardHumidityPct=value("B", 4, 255), inaBusV=value("H", 5, 65535, 1000),
                    inaCurrentMa=value("h", 7, 32767, 10), lectura=payload[9],
                    **{name: bool(flags & (1 << bit)) for bit, name in enumerate(
                        ("gpsFix", "usbPowered", "charging", "gpsActive", "enVuelo", "corteEnCurso", "cortado"))})
    elif fport == 30:
        seq, rssi, snr = struct.unpack("<Bhb", payload)
        meta.update(seq=seq, downlinkRssiDbm=rssi, downlinkSnrDb=snr / 4)
    else:
        event, reason, seq, attempt = payload[:4]
        if event not in (1, 2, 3) or reason not in (1, 2, 3, 4, 5):
            raise ValueError("Radiosonda: evento o motivo de corte desconocido")
        meta.update(evento={1: "inicio", 2: "confirmado", 3: "sin_confirmar"}[event],
                    motivo={1: "altura", 2: "tiempo", 3: "reventon", 4: "downlink", 5: "consola"}[reason],
                    seq=seq, intento=attempt, altitudeM=value("H", 4, 65535), tVueloS=value("H", 6, 65535),
                    verticalSpeedMs=value("h", 8, 32767, 10),
                    altitudeSource=("gps" if payload[10] & 1 else "barometrica") if value("H", 4, 65535) is not None else None,
                    enVuelo=bool(payload[10] & 2))
    ranges = {"temperatureC": (-127, 127), "pressureHpa": (0, 1270), "humidityPct": (0, 100), "batteryV": (0, 5.08)}
    for key, (lower, upper) in ranges.items():
        reading = fields.get(key)
        if reading is not None and not lower <= reading <= upper:
            raise ValueError(f"Radiosonda: {key} fuera de rango")
    if meta.get("batteryPct") is not None and not 0 <= meta["batteryPct"] <= 100:
        raise ValueError("Radiosonda: batería porcentual fuera de rango")
    meta["presentFields"] = list(fields)
    meta["presentDeviceFields"] = [k for k in ("gpsFix", "gpsActive", "satellites", "usbPowered", "charging", "batteryPct") if k in meta]
    return {**fields, "metadata": meta}
