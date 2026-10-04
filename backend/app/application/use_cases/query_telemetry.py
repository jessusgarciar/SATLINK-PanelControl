import asyncio
import csv
import io
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from app.application.ports.telemetry import TelemetryExport, TelemetryQueries
from app.domain.entities.telemetry import JsonObject

SCALARS = ("id", "missionId", "receivedAt", "frameCounter", "latitude", "longitude",
           "altitudeGpsM", "relativeAltitudeM", "altitudeBarometricM", "verticalSpeedMs",
           "temperatureC", "pressureHpa", "humidityPct", "batteryV", "rssiDbm", "snrDb")
GROUPS = {"device": ("gpsActive", "gpsFix", "satellites", "batteryPct", "charging", "usbPowered"),
          "radio": ("gatewayId", "frequencyHz", "dataRate", "fPort")}
CSV_COLUMNS = [*SCALARS, *(f"{group}_{key}" for group, keys in GROUPS.items() for key in keys),
               "source", "applicationId", "devEui", "raw_json"]


def interval(from_time: datetime | None, to_time: datetime | None) -> tuple[datetime | None, datetime]:
    end = to_time if to_time is not None else datetime.now(timezone.utc)
    if end.tzinfo is None or (from_time is not None and from_time.tzinfo is None):
        raise ValueError("Se requiere zona horaria")
    if from_time is not None and from_time >= end:
        raise ValueError("from debe ser anterior a to")
    return from_time, end


class QueryTelemetry:
    def __init__(self, store: TelemetryQueries) -> None:
        self.store = store

    async def window(self, mission_id: str, from_time: datetime | None = None,
                     to_time: datetime | None = None) -> JsonObject:
        start, end = interval(from_time, to_time)
        return await self.store.window(mission_id, start, end)

    async def export(self, mission_id: str, from_time: datetime | None = None,
                     to_time: datetime | None = None) -> "CsvExport":
        start, end = interval(from_time, to_time)
        # El repositorio valida misión y abre el cursor antes de enviar cabeceras HTTP.
        return CsvExport(await self.store.export(mission_id, start, end))


class CsvExport:
    def __init__(self, rows: TelemetryExport) -> None:
        self.rows = rows

    async def aclose(self) -> None:
        await self.rows.aclose()

    async def chunks(self) -> AsyncIterator[bytes]:
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer)
        def chunk(values: list) -> bytes:
            buffer.seek(0)
            buffer.truncate(0)
            writer.writerow(values)
            return buffer.getvalue().encode("utf-8")
        try:
            yield b"\xef\xbb\xbf" + chunk(CSV_COLUMNS)
            async for row in self.rows:
                data = row["telemetry"]
                values = [data.get(key) for key in SCALARS]
                for group, keys in GROUPS.items():
                    metadata = data.get(group) or {}
                    values.extend(metadata.get(key) for key in keys)
                values.extend((row["source"], row.get("applicationId"), row.get("devEui"),
                               None if row.get("raw_json") is None else json.dumps(row["raw_json"], ensure_ascii=False,
                                                       separators=(",", ":"))))
                yield chunk(values)
                await asyncio.sleep(0)
        finally:
            buffer.close()
            await self.aclose()
