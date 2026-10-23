"""Diagnóstico local de identidad, sin mostrar claves OTAA ni credenciales del broker."""
import asyncio
import json
import re
from pathlib import Path
from app.bootstrap.config import Settings
from app.infrastructure.database.store import PostgresStore
from app.infrastructure.mqtt.consumer import device_uplink_topic


async def check_identity(settings: Settings, mission_path: Path, firmware_path: Path) -> dict:
    local = json.loads(await asyncio.to_thread(mission_path.read_text, encoding="utf-8-sig"))
    firmware = await asyncio.to_thread(firmware_path.read_text, encoding="utf-8-sig")
    match = re.search(r"^\s*#define\s+PICARO_DEV_EUI\s+0x([0-9a-fA-F]{16})(?:ULL|ull)?\b", firmware, re.MULTILINE)
    if match is None:
        raise ValueError("El archivo de firmware no contiene PICARO_DEV_EUI válido")
    expected = match[1].lower()
    store = PostgresStore(settings.database_url)
    try:
        snapshot = await store.dashboard(local["id"], 1)
        mission = snapshot["mission"]
        bound = await store.find_mission(settings.source, local["applicationId"], local["deviceEui"])
        matches = (expected == local["deviceEui"] == mission["deviceEui"] and
                   local["applicationId"] == mission["applicationId"] and
                   local["source"] == settings.source and bound is not None and bound.id == local["id"])
        return {"status": "matched" if matches else "mismatch", "missionId": local["id"],
                "firmwareDeviceEui": expected, "localDeviceEui": local["deviceEui"],
                "databaseDeviceEui": mission["deviceEui"], "applicationId": mission["applicationId"],
                "mqttTopic": device_uplink_topic(local["applicationId"], local["deviceEui"]),
                "staleAfterSeconds": mission["staleAfterSeconds"],
                "latestTelemetryAt": snapshot["telemetry"][-1]["receivedAt"] if snapshot["telemetry"] else None}
    finally:
        await store.close()
