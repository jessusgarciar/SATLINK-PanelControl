import asyncio
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from anyio import CancelScope
from app.domain.entities.telemetry import ConfigurationConflict, JsonObject
from app.infrastructure.database.store import PostgresStore
from app.presentation.schemas.api import MissionConfig, MissionParameters


def replace_file(path: Path, contents: str) -> None:
    """Replace within the same directory so readers never observe partial JSON."""
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class MissionSettings:
    def __init__(self, store: PostgresStore, path: Path) -> None:
        self.store, self.path = store, path
        self.lock = asyncio.Lock()

    async def populate_application_name(self, mission: JsonObject) -> JsonObject:
        """Backfill the existing active mission from its matching local configuration."""
        if mission.get("applicationName"):
            return mission
        async with self.lock:
            try:
                raw = json.loads(await asyncio.to_thread(self.path.read_text, encoding="utf-8-sig"))
                local = MissionConfig.model_validate(raw).model_dump(mode="json")
            except (OSError, ValueError):
                return mission
            name = local.get("applicationName")
            if not name or local["id"] != mission["id"] or any(local[key] != mission.get(key)
                    for key in ("applicationId", "deviceEui")):
                return mission
            async with self.store.edit_mission(mission["id"]) as (configuration, snapshot):
                if any(local[key] != configuration[key] for key in ("source", "applicationId", "deviceEui")):
                    return mission
                name = configuration.get("applicationName") or name
                configuration["applicationName"] = name
                snapshot.update(applicationName=name, updatedAt=datetime.now(timezone.utc).isoformat())
            return {**mission, "applicationName": name, "updatedAt": snapshot["updatedAt"]}

    async def update(self, mission_id: str, parameters: MissionParameters) -> JsonObject:
        async with self.lock:
            original = await asyncio.to_thread(self.path.read_text, encoding="utf-8-sig")
            raw = json.loads(original)
            local = MissionConfig.model_validate(raw).model_dump(mode="json")
            changes = parameters.model_dump(mode="json")
            written = False
            # Finish file replacement and DB commit together, including client cancellation.
            with CancelScope(shield=True):
                try:
                    async with self.store.edit_mission(mission_id) as (configuration, snapshot):
                        if local["id"] != mission_id or any(local[key] != configuration[key] for key in
                                ("source", "applicationId", "deviceEui")):
                            raise ConfigurationConflict("El archivo local no corresponde a la misión activa")
                        configuration.update(changes)
                        name = configuration.get("applicationName") or local.get("applicationName")
                        if name:
                            configuration["applicationName"] = name
                        snapshot.update(changes, updatedAt=datetime.now(timezone.utc).isoformat())
                        snapshot.update(applicationId=configuration["applicationId"],
                                        applicationName=configuration.get("applicationName"))
                        contents = json.dumps({**raw, **changes, **({"applicationName": name} if name else {})}, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
                        await asyncio.to_thread(replace_file, self.path, contents)
                        written = True
                    return snapshot
                except BaseException:
                    if written:
                        await asyncio.to_thread(replace_file, self.path, original)
                    raise
