import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from collections.abc import Coroutine
from typing import Any
import uvicorn
from app.bootstrap.app import create_app
from app.bootstrap.config import Settings
from app.infrastructure.database.store import PostgresStore
from app.infrastructure.mqtt.consumer import device_uplink_topic
from app.presentation.schemas.api import MissionConfig


def run_async(coroutine: Coroutine[Any, Any, Any]) -> Any:
    # aiomqtt 2 y psycopg asíncrono requieren SelectorEventLoop en Windows.
    if sys.platform == "win32":
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            return runner.run(coroutine)
    return asyncio.run(coroutine)


async def initialize(settings: Settings, path: Path) -> None:
    raw = json.loads(await asyncio.to_thread(path.read_text, encoding="utf-8-sig"))
    config = validate_mission(raw, settings)
    store = PostgresStore(settings.database_url)
    try:
        await store.initialize_mission(config)
        print("Misión inicializada:", config["id"])
    finally:
        await store.close()


def validate_mission(raw: dict, settings: Settings) -> dict:
    config = MissionConfig.model_validate(raw).model_dump(mode="json")
    if config["source"] != settings.source:
        raise ValueError("source de la misión debe coincidir con SATLINK_CHIRPSTACK_SOURCE")
    return config


def configured_mqtt_topic(settings: Settings, mission_path: Path | None = None) -> str | None:
    if not settings.mqtt_enabled:
        return None
    path = mission_path or Path(__file__).resolve().parents[2] / "mission.local.json"
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    mission = validate_mission(raw, settings)
    return device_uplink_topic(mission["applicationId"], mission["deviceEui"])


def main() -> None:
    parser = argparse.ArgumentParser(description="SATLINK local: telemetría e historial")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve")
    init = commands.add_parser("init-mission")
    init.add_argument("--file", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    if args.command == "serve":
        # Un único worker y sin cabeceras proxy: esta versión es solo local.
        mqtt_topic = configured_mqtt_topic(settings)
        server = uvicorn.Server(uvicorn.Config(create_app(settings, mqtt_topic=mqtt_topic), host="127.0.0.1",
                                               port=settings.port, workers=1, proxy_headers=False))
        run_async(server.serve())
    else:
        run_async(initialize(settings, args.file))


if __name__ == "__main__":
    main()
