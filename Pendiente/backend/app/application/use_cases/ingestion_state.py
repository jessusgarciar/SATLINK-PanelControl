from datetime import datetime, timezone
from typing import Literal
from app.domain.entities.telemetry import JsonObject
from app.application.ports.telemetry import IngestionPublisher

IngestionStatus = Literal["disabled", "connecting", "connected", "reconnecting", "offline"]


class IngestionState:
    """Estado del transporte; no certifica recepción de radio ni persistencia."""
    def __init__(self, source: str, enabled: bool, hub: IngestionPublisher) -> None:
        self.source, self.hub = source, hub
        self.status: IngestionStatus = "connecting" if enabled else "disabled"
        self.updated_at = datetime.now(timezone.utc)
        self.missions: set[str] = set()

    def snapshot(self, source: str | None = None) -> JsonObject:
        return {"source": source or self.source,
                "status": self.status if source is None or source == self.source else "disabled",
                "updatedAt": self.updated_at.isoformat().replace("+00:00", "Z")}

    async def update(self, status: IngestionStatus) -> None:
        if status not in ("disabled", "connecting", "connected", "reconnecting", "offline"):
            raise ValueError("Estado MQTT inválido")
        if self.status == status:
            return
        self.status, self.updated_at = status, datetime.now(timezone.utc)
        await self.hub.publish_ingestion(self.snapshot(), self.missions)
