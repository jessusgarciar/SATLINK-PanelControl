from datetime import datetime, timezone
from app.application.ports.commands import CommandPublisher, CommandStore, CommandTransport
from app.domain.entities.commands import CommandUnavailable
from app.domain.entities.telemetry import JsonObject


class RequestCommand:
    def __init__(self, store: CommandStore, publisher: CommandPublisher,
                 transport: CommandTransport | None) -> None:
        self.store, self.publisher, self.transport = store, publisher, transport

    async def execute(self, mission: JsonObject, request_id: str, kind: str) -> JsonObject:
        if self.transport is None or not self.transport.supports(mission):
            raise CommandUnavailable("Comandos pendientes del protocolo de firmware y de la identidad del dispositivo")
        command, created = await self.store.reserve_command(mission["id"], request_id, kind, datetime.now(timezone.utc))
        if not created:
            return command
        self.publisher.send(mission["id"], {"type": "command", "data": command})
        # Nunca reintentar un envío incierto: la solicitud persistida mantiene la idempotencia.
        try:
            await self.transport.send(mission, command)
            evidence = "Publicación MQTT confirmada por el broker; pendiente de gateway y de la Heltec. No acredita ejecución."
        except Exception:
            evidence = "Publicación sin confirmación: resultado incierto. No se reintentó. Revisar bitácora antes de otra solicitud."
        return await self.update(mission["id"], command["id"], "pending", evidence)

    async def update(self, mission_id: str, command_id: str, status: str, evidence: str,
                     *, started_at: datetime | None = None) -> JsonObject:
        """Entrada interna para evidencia ya validada y correlacionada por un adaptador."""
        command, mission = await self.store.command_evidence(
            mission_id, command_id, status, evidence, started_at=started_at)
        self.publisher.send(mission_id, {"type": "command", "data": command})
        if mission is not None:
            self.publisher.send(mission_id, {"type": "mission", "data": mission})
        return command
