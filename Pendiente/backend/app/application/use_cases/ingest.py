import logging
from uuid import uuid4
from app.application.ports.telemetry import TelemetryPublisher, TelemetryStore, UplinkDecoder
from app.domain.entities.telemetry import JsonObject

logger = logging.getLogger(__name__)


class IngestTelemetry:
    def __init__(self, store: TelemetryStore, publisher: TelemetryPublisher,
                 source: str, decoder: UplinkDecoder) -> None:
        self.store, self.publisher, self.source, self.decoder = store, publisher, source, decoder

    async def execute(self, topic: str, payload: bytes) -> JsonObject | None:
        try:
            event = self.decoder.decode(topic, payload, self.source)
        except ValueError as exc:
            await self.store.reject(self.source, topic, payload, str(exc))
            logger.warning("Uplink rechazado: formato inválido")
            return None
        mission = await self.store.find_mission(self.source, event.application_id, event.dev_eui)
        if mission is None:
            await self.store.reject(self.source, topic, payload, "Dispositivo/aplicación sin misión configurada")
            return None
        altitude = event.measurements["altitudeGpsM"]
        telemetry = {
            **event.measurements,
            "id": str(uuid4()), "missionId": mission.id,
            "receivedAt": event.received_at.isoformat().replace("+00:00", "Z"),
            "frameCounter": event.frame_counter,
            "relativeAltitudeM": None if altitude is None else altitude - mission.snapshot["launch"]["altitudeM"],
            "altitudeBarometricM": None, "verticalSpeedMs": None,
        }
        if not await self.store.persist(mission, event, telemetry):
            return None
        try:
            await self.publisher.publish(mission.id, telemetry)
        except Exception:
            # El snapshot y el historial recuperan una emisión fallida tras el commit.
            logger.exception("Telemetría guardada; falló la publicación WebSocket")
        return telemetry
