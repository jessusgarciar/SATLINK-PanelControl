"""Acceptance check against an already running local station; never publishes uplinks."""
import asyncio
import base64
import binascii
import csv
import io
import json
import ssl
from datetime import datetime, timedelta, timezone
from statistics import median
from uuid import uuid4

import aiomqtt
import httpx
from websockets.asyncio.client import connect

from app.bootstrap.config import Settings
from app.infrastructure.mqtt.consumer import device_uplink_topic
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.schemas.api import DashboardDTO, HistoryDTO, TelemetryDTO
from app.presentation.schemas.uplink import ChirpStackDecoder, utc_time


class LiveCheckError(ValueError):
    pass


def sample_key(sample: dict) -> tuple[int, datetime]:
    return sample["frameCounter"], utc_time(sample["receivedAt"])


def verify_archive(rows: list[dict], streamed: dict[str, dict], observed: dict,
                   mission: dict) -> list[dict]:
    """Correlate raw MQTT, CSV and WebSocket by the archived deduplication ID."""
    decoder = ChirpStackDecoder(decode_payload)
    verified = []
    seen = set()
    topic = device_uplink_topic(mission["applicationId"], mission["deviceEui"])
    for row in rows:
        raw = json.loads(row["raw_json"]) if row.get("raw_json") else {}
        event_id = raw.get("deduplicationId")
        if event_id not in observed:
            continue
        if event_id in seen:
            raise LiveCheckError("Un evento MQTT aparece duplicado en el CSV")
        seen.add(event_id)
        if (row["source"] != mission["source"] or
                row["applicationId"] != mission["applicationId"] or
                row["devEui"] != mission["deviceEui"] or row["missionId"] != mission["id"]):
            raise LiveCheckError("El archivo contiene un origen o una misión incorrectos")
        original = observed[event_id]
        if raw != original.raw_event:
            raise LiveCheckError("El evento archivado difiere del observado en MQTT")
        sample = streamed.get(row["id"])
        if sample is None:
            continue
        decoded = decoder.decode(topic, json.dumps(raw).encode(), mission["source"])
        expected = {**decoded.measurements, "frameCounter": decoded.frame_counter,
                    "missionId": mission["id"]}
        altitude = expected["altitudeGpsM"]
        expected["relativeAltitudeM"] = None if altitude is None else altitude - mission["launch"]["altitudeM"]
        expected.update(altitudeBarometricM=None, verticalSpeedMs=decoded.measurements.get("verticalSpeedMs"))
        if utc_time(sample["receivedAt"]) != decoded.received_at:
            raise LiveCheckError("La fecha WebSocket difiere del evento MQTT")
        for field, value in expected.items():
            if sample.get(field) != value:
                raise LiveCheckError(f"El campo {field} difiere entre MQTT y WebSocket")
            if isinstance(value, dict):
                for name, child in value.items():
                    if row[f"{field}_{name}"] != csv_value(child):
                        raise LiveCheckError(f"El campo CSV {field}_{name} no coincide")
            elif row[field] != csv_value(value):
                # PostgreSQL/DTO puede serializar 1 como 1.0: comparar números por valor.
                if not (type(value) in (int, float) and row[field] and float(row[field]) == value):
                    raise LiveCheckError(f"El campo CSV {field} no coincide")
        if utc_time(row["receivedAt"]) != decoded.received_at:
            raise LiveCheckError("La fecha del CSV difiere del evento MQTT")
        verified.append(sample)
    return verified


def csv_value(value: object) -> str:
    return "" if value is None else str(value)


async def check_live(settings: Settings, mission: dict, samples: int = 10,
                     timeout: float = 600, report: dict | None = None) -> dict:
    if samples < 1 or timeout <= 0:
        raise LiveCheckError("samples y timeout deben ser positivos")
    if not settings.mqtt_enabled:
        raise LiveCheckError("MQTT está deshabilitado en la configuración efectiva")
    report = report if report is not None else {}
    report.update(status="running", missionId=mission["id"], requestedSamples=samples,
                  startedAt=datetime.now(timezone.utc).isoformat(), checks={}, samples=[],
                  mqttEvents=0, websocketSamples=0)
    checks = report["checks"]
    observed, streamed, arrival = {}, {}, {}
    queue = asyncio.Queue(maxsize=4096)
    topic = device_uplink_topic(mission["applicationId"], mission["deviceEui"])
    base = f"http://127.0.0.1:{settings.port}/api/v1/missions/{mission['id']}"
    decoder = ChirpStackDecoder(decode_payload)

    async def mqtt_messages() -> None:
        async with aiomqtt.Client(hostname=settings.mqtt_host, port=settings.mqtt_port,
                username=settings.mqtt_username, password=settings.mqtt_password,
                identifier=f"satlink-check-{uuid4().hex[:12]}", clean_session=True,
                tls_context=ssl.create_default_context() if settings.mqtt_tls else None) as client:
            await client.subscribe(topic, qos=1)
            checks["mqttSubscription"] = True
            print("[CHECK] Suscripción de diagnóstico aceptada; esperando uplinks nuevos", flush=True)
            async for message in client.messages:
                if message.retain:
                    continue
                # Solo forma del mensaje: conservar diagnóstico sin volcar el payload.
                shape = {"fPort": None, "payloadBytes": None}
                try:
                    envelope = json.loads(message.payload)
                    if isinstance(envelope, dict):
                        port = envelope.get("fPort")
                        shape["fPort"] = port if type(port) is int else None
                        shape["payloadBytes"] = len(base64.b64decode(envelope.get("data", ""), validate=True))
                except (ValueError, TypeError, binascii.Error):
                    pass
                report["lastUplink"] = shape
                try:
                    event = decoder.decode(str(message.topic), bytes(message.payload), settings.source)
                except ValueError:
                    raise LiveCheckError("Uplink incompatible: requiere PICARO FULL (puerto 10, 19 bytes) o VUELO (puerto 17, 11 bytes)") from None
                await queue.put(("mqtt", event))

    async def websocket_messages() -> None:
        async with connect(base.replace("http://", "ws://") + "/stream",
                           origin=f"http://127.0.0.1:{settings.port}", proxy=None,
                           open_timeout=10, close_timeout=2) as websocket:
            checks["websocket"] = True
            async for raw in websocket:
                message = json.loads(raw)
                if message.get("type") == "telemetry":
                    sample = TelemetryDTO.model_validate(message["data"]).model_dump(mode="json")
                    await queue.put(("telemetry", sample))
                elif message.get("type") == "ingestion":
                    report["ingestionStatus"] = message["data"]["status"]
            raise LiveCheckError("El WebSocket se cerró antes de completar la comprobación")

    async def supervise(function) -> None:
        try:
            await function()
        except Exception as exc:
            await queue.put(("error", exc))

    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        snapshot = DashboardDTO.model_validate((await client.get(base + "/dashboard", params={"limit": 1})).raise_for_status().json())
        if snapshot.mission.id != mission["id"] or snapshot.mission.deviceEui != mission["deviceEui"]:
            raise LiveCheckError("El dashboard no corresponde a la misión y dispositivo configurados")
        checks["dashboard"] = True
        tasks = [asyncio.create_task(supervise(mqtt_messages)), asyncio.create_task(supervise(websocket_messages))]
        try:
            async with asyncio.timeout(timeout):
                while True:
                    kind, value = await queue.get()
                    if kind == "error":
                        raise value
                    if kind == "mqtt":
                        age = (datetime.now(timezone.utc) - value.received_at).total_seconds()
                        if age < -30 or age > mission["staleAfterSeconds"]:
                            raise LiveCheckError("El uplink recibido tiene una fecha futura u obsoleta; revisar relojes e intervalo")
                        observed[value.deduplication_id] = value
                    else:
                        if value["missionId"] != mission["id"]:
                            raise LiveCheckError("WebSocket entregó telemetría de otra misión")
                        streamed[value["id"]] = value
                        arrival[value["id"]] = datetime.now(timezone.utc)
                    report["mqttEvents"] = len(observed)
                    report["websocketSamples"] = len(streamed)
                    keys = {sample_key(sample) for sample in streamed.values()}
                    matched = [event for event in observed.values() if (event.frame_counter, event.received_at) in keys]
                    if len(matched) >= samples:
                        break
                    if kind == "mqtt":
                        print(f"[CHECK] MQTT {len(observed)}/{samples}; WebSocket {len(streamed)}", flush=True)
                start = min(event.received_at for event in matched)
                end = max(event.received_at for event in matched) + timedelta(microseconds=1)
                params = {"from": start.isoformat(), "to": end.isoformat()}
                response = (await client.get(base + "/telemetry/export.csv", params=params)).raise_for_status()
                rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
                verified = verify_archive(rows, streamed, observed, mission)
                if len(verified) < samples:
                    raise LiveCheckError("No se correlacionaron suficientes eventos entre MQTT, CSV y WebSocket")
                checks.update(payload=True, persistedCsv=True, values=True)
                # Consultar HTTP de nuevo comprueba recuperación independiente del stream.
                history = {}
                cursor = None
                while True:
                    page_params = {**params, "limit": 200}
                    if cursor:
                        page_params["cursor"] = cursor
                    page = HistoryDTO.model_validate((await client.get(base + "/telemetry", params=page_params)).raise_for_status().json())
                    history.update((item.id, item.model_dump(mode="json")) for item in page.items)
                    cursor = page.nextCursor
                    if cursor is None:
                        break
                if any(history.get(sample["id"]) != sample for sample in verified):
                    raise LiveCheckError("El historial HTTP no recupera los mismos valores emitidos por WebSocket")
                checks["history"] = True
                latest = DashboardDTO.model_validate((await client.get(base + "/dashboard")).raise_for_status().json())
                newest = max(verified, key=lambda sample: utc_time(sample["receivedAt"]))
                dashboard_samples = {item.id: item.model_dump(mode="json") for item in latest.telemetry}
                if dashboard_samples.get(newest["id"]) != newest:
                    raise LiveCheckError("El dashboard no recupera la última muestra verificada")
                checks["dashboardRecovery"] = True
                if latest.ingestion is None or latest.ingestion.status != "connected":
                    raise LiveCheckError("El consumidor MQTT del backend no está conectado al finalizar")
                checks["backendMqtt"] = True
                report["ingestionStatus"] = latest.ingestion.status
                report["samples"] = [{"id": sample["id"], "frameCounter": sample["frameCounter"],
                    "receivedAt": sample["receivedAt"],
                    "observedDelaySeconds": round((arrival[sample["id"]] - utc_time(sample["receivedAt"])).total_seconds(), 3)}
                    for sample in verified]
                times = sorted({utc_time(sample["receivedAt"]) for sample in verified})
                intervals = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
                report["medianIntervalSeconds"] = median(intervals) if intervals else None
                report["verifiedSamples"] = len(verified)
                report["status"] = "passed"
                return report
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            report["finishedAt"] = datetime.now(timezone.utc).isoformat()
