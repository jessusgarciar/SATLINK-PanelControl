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
    identity = commands.add_parser("check-identity", help="Comparar DevEUI del firmware, misión local y PostgreSQL")
    identity.add_argument("--file", type=Path, default=Path(__file__).resolve().parents[2] / "mission.local.json")
    identity.add_argument("--firmware", type=Path, required=True)
    check = commands.add_parser("check-live", help="Verificar MQTT, WebSocket, historial y CSV con uplinks nuevos")
    check.add_argument("--file", type=Path, default=Path(__file__).resolve().parents[2] / "mission.local.json")
    check.add_argument("--samples", type=int, default=10)
    check.add_argument("--timeout", type=float, default=600)
    check.add_argument("--report", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    if args.command == "serve":
        # Un único worker y sin cabeceras proxy: esta versión es solo local.
        mqtt_topic = configured_mqtt_topic(settings)
        server = uvicorn.Server(uvicorn.Config(create_app(settings, mqtt_topic=mqtt_topic), host="127.0.0.1",
                                               port=settings.port, workers=1, proxy_headers=False))
        run_async(server.serve())
    elif args.command == "init-mission":
        run_async(initialize(settings, args.file))
    elif args.command == "check-identity":
        from app.bootstrap.identity import check_identity
        result = run_async(check_identity(settings, args.file, args.firmware))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if result["status"] != "matched":
            raise SystemExit(1)
    else:
        from app.bootstrap.check_live import LiveCheckError, check_live
        report = {}
        try:
            if args.report is not None and not args.report.parent.is_dir():
                raise LiveCheckError("La carpeta del informe no existe")
            mission = validate_mission(json.loads(args.file.read_text(encoding="utf-8-sig")), settings)
            run_async(check_live(settings, mission, args.samples, args.timeout, report))
        except KeyboardInterrupt:
            report.update(status="cancelled", reason="Comprobación interrumpida por el operador")
        except Exception as exc:
            timeout_reason = "Tiempo agotado esperando conexión con los servicios locales"
            if report.get("checks", {}).get("mqttSubscription"):
                timeout_reason = (
                    "Conexión MQTT aceptada, pero no llegaron uplinks nuevos del dispositivo durante la observación"
                    if not report.get("mqttEvents") else
                    "Llegaron uplinks MQTT, pero no se completó su correlación con WebSocket y el archivo")
            reason = (str(exc) if isinstance(exc, LiveCheckError) else
                      timeout_reason if isinstance(exc, TimeoutError) else
                      f"Fallo de comprobación ({type(exc).__name__}); revisar servicios y logs locales")
            report.update(status="failed", reason=reason)
        if args.report is not None and args.report.parent.is_dir():
            args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False))
        if report["status"] != "passed":
            raise SystemExit(130 if report["status"] == "cancelled" else 1)


if __name__ == "__main__":
    main()
