import logging
import ssl
from asyncio import sleep
from collections.abc import Awaitable, Callable
import aiomqtt

logger = logging.getLogger(__name__)
LEGACY_UPLINK_TOPIC = "application/+/device/+/event/up"


def device_uplink_topic(application_id: str, device_eui: str) -> str:
    return f"application/{application_id}/device/{device_eui}/event/up"


def _safe_failure(exc: Exception, username: str | None, password: str | None) -> str:
    detail = getattr(exc, "reason_str", None) or str(exc)
    for credential in (username, password):
        if credential:
            detail = detail.replace(credential, "[redacted]")
    return f"{type(exc).__name__}: {detail[:200]}"


async def consume(host: str, port: int, username: str | None, password: str | None,
                  tls: bool, identifier: str, topic: str,
                  ingest: Callable[[str, bytes], Awaitable[object]],
                  on_status: Callable[[str], Awaitable[None]] | None = None,
                  event_topics: tuple[str, ...] = ()) -> None:
    try:
        await _consume(host, port, username, password, tls, identifier, topic, ingest, on_status, event_topics)
    finally:
        if on_status is not None:
            await on_status("offline")


async def _consume(host: str, port: int, username: str | None, password: str | None,
                   tls: bool, identifier: str, topic: str,
                   ingest: Callable[[str, bytes], Awaitable[object]],
                   on_status: Callable[[str], Awaitable[None]] | None = None,
                   event_topics: tuple[str, ...] = ()) -> None:
    async def status(value: str) -> None:
        if on_status is not None:
            await on_status(value)
    delay = 1
    await status("connecting")
    while True:
        stage = "connection"
        try:
            async with aiomqtt.Client(hostname=host, port=port, username=username, password=password,
                                      identifier=identifier, clean_session=False,
                                      tls_context=ssl.create_default_context() if tls else None) as client:
                # El filtro wildcard pudo quedar persistido por una versión anterior del consumidor.
                stage = "legacy subscription cleanup"
                await client.unsubscribe(LEGACY_UPLINK_TOPIC)
                stage = "subscription"
                await client.subscribe(topic, qos=1)
                for event_topic in event_topics:
                    await client.subscribe(event_topic, qos=1)
                logger.info("Suscripción MQTT activa: %s", topic)
                await status("connected")
                delay = 1
                async for message in client.messages:
                    if str(message.topic) in event_topics and getattr(message, "retain", False):
                        continue
                    if not isinstance(message.payload, bytes):
                        continue
                    # Reintentar la misma muestra si PostgreSQL no está disponible.
                    # La clave de evento hace inocuo un reintento posterior al commit.
                    retry_delay = 1
                    while True:
                        try:
                            await ingest(str(message.topic), message.payload)
                            break
                        except Exception:
                            logger.exception("No se pudo guardar el uplink; se reintentará")
                            await sleep(retry_delay)
                            retry_delay = min(retry_delay * 2, 30)
        except (aiomqtt.MqttError, OSError) as exc:
            await status("reconnecting")
            logger.warning("Fallo MQTT en %s (%s); reintentando en %s s",
                           stage, _safe_failure(exc, username, password), delay)
            await sleep(delay)
            delay = min(delay * 2, 30)
