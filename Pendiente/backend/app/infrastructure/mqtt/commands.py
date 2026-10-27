"""Downlinks explícitos: sin perfil de firmware no se inventan bytes ni se publica."""
import base64
import json
import re
import ssl
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4
import aiomqtt
from app.application.use_cases.commands import RequestCommand
from app.bootstrap.config import Settings
from app.domain.entities.commands import COMMAND_TYPES
from app.domain.entities.telemetry import JsonObject


@dataclass(frozen=True)
class CommandProfile:
    mission_id: str
    application_id: str
    device_eui: str
    source: str
    fport: int
    payload_hex: dict[str, str]
    protocol: str = "legacy"

    @classmethod
    def load(cls, path: Path) -> "CommandProfile":
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if raw.get("protocol") == "radiosonda-meca-v1":
            profile = cls(raw["missionId"], raw["applicationId"], raw["deviceEui"], raw["source"],
                          30, {"PING": "", "RELEASE_NOW": ""}, "radiosonda-meca-v1")
            if (not all(isinstance(v, str) and v and not re.search(r"[/+#]", v) for v in
                    (profile.mission_id, profile.application_id, profile.source)) or
                    not isinstance(profile.device_eui, str) or not re.fullmatch(r"[0-9a-f]{16}", profile.device_eui)):
                raise ValueError("Identidad de perfil radiosonda inválida")
            return profile
        profile = cls(raw["missionId"], raw["applicationId"], raw["deviceEui"], raw["source"],
                      raw["fPort"], raw["payloadHex"])
        if (not all(isinstance(v, str) and v and not re.search(r"[/+#]", v) for v in
                    (profile.mission_id, profile.application_id, profile.source)) or
                not isinstance(profile.device_eui, str) or not re.fullmatch(r"[0-9a-f]{16}", profile.device_eui) or
                type(profile.fport) is not int or not 1 <= profile.fport <= 223 or
                not isinstance(profile.payload_hex, dict) or not profile.payload_hex or
                any(k not in COMMAND_TYPES or k == "RELEASE_NOW" for k in profile.payload_hex)):
            raise ValueError("Perfil de comandos inválido")
        for kind, template in profile.payload_hex.items():
            if not isinstance(template, str) or "{requestId}" not in template:
                raise ValueError("Cada comando debe codificar {requestId} para correlacionar respuestas")
            if kind == "START_MISSION" and "{watchdogSeconds}" not in template:
                raise ValueError("START_MISSION debe codificar {watchdogSeconds}")
            profile.encode({"id": str(UUID(int=0)), "type": kind, "watchdogSeconds": 3300})
        return profile

    def encode(self, command: JsonObject) -> bytes:
        if self.protocol == "radiosonda-meca-v1":
            seq = command.get("seq")
            if type(seq) is not int or not 1 <= seq <= 255:
                raise ValueError("Secuencia persistida requerida")
            if command["type"] == "PING":
                return bytes([seq])
            if command["type"] == "RELEASE_NOW":
                return b"CORT" + bytes([seq])
            raise ValueError("Comando no soportado por radiosonda")
        template = self.payload_hex[command["type"]]
        value = template.replace("{requestId}", UUID(command["id"]).hex).replace(
            "{watchdogSeconds}", int(command["watchdogSeconds"]).to_bytes(4, "big").hex())
        payload = bytes.fromhex(value)
        if not 1 <= len(payload) <= 242:
            raise ValueError("Longitud de comando inválida")
        return payload


class ChirpStackCommands:
    def __init__(self, settings: Settings, profile: CommandProfile) -> None:
        self.settings, self.profile = settings, profile

    @property
    def event_topics(self) -> tuple[str, ...]:
        base = f"application/{self.profile.application_id}/device/{self.profile.device_eui}/event"
        return (base + "/txack", base + "/ack")

    def supports(self, mission: JsonObject) -> bool:
        return (mission.get("telemetryProtocol", "legacy") == self.profile.protocol and
                mission["id"] == self.profile.mission_id and
                mission.get("applicationId") == self.profile.application_id and
                mission["deviceEui"] == self.profile.device_eui)

    async def send(self, mission: JsonObject, command: JsonObject) -> None:
        if not self.supports(mission):
            raise ValueError("El perfil de comandos no corresponde a esta misión/dispositivo")
        radio = self.profile.protocol == "radiosonda-meca-v1"
        message = {"id": command["id"], "devEui": self.profile.device_eui, "confirmed": not radio,
                   "fPort": (31 if command["type"] == "RELEASE_NOW" else 30) if radio else self.profile.fport}
        message["data"] = base64.b64encode(self.profile.encode(command)).decode("ascii")
        topic = f"application/{self.profile.application_id}/device/{self.profile.device_eui}/command/down"
        settings = self.settings
        # Cliente separado: no expulsa al consumidor de telemetría. Sin reconexión/reenvío automático.
        async with aiomqtt.Client(hostname=settings.mqtt_host, port=settings.mqtt_port,
                username=settings.mqtt_username, password=settings.mqtt_password,
                identifier=f"system-command-{uuid4().hex[:12]}", clean_session=True, timeout=4,
                tls_context=ssl.create_default_context() if settings.mqtt_tls else None) as client:
            await client.publish(topic, json.dumps(message), qos=1, retain=False, timeout=4)

    async def ingest_evidence(self, topic: str, payload: bytes, service: RequestCommand) -> None:
        if topic not in self.event_topics or len(payload) > 262144:
            return
        try:
            event = json.loads(payload)
            device = event["deviceInfo"]
            if device["applicationId"] != self.profile.application_id or device["devEui"] != self.profile.device_eui:
                return
            identifier = str(UUID(event["queueItemId"]))
            if topic.endswith("/txack"):
                status, evidence = "sent", "Gateway confirmó la programación del downlink (txack); no acredita recepción ni ejecución."
            else:
                acknowledged = event.get("acknowledged", False)
                if type(acknowledged) is not bool:
                    return
                status, evidence = (("received", "ACK LoRaWAN del dispositivo; no acredita ejecución del comando.")
                    if acknowledged else ("expired", "ChirpStack notificó que no recibió ACK del downlink; ejecución no confirmada."))
            await service.update(self.profile.mission_id, identifier, status, evidence)
        except (ValueError, KeyError, TypeError):
            # Eventos ajenos o inválidos no cambian la bitácora ni bloquean la telemetría.
            return
