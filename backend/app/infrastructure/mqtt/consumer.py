import logging
import ssl
from asyncio import sleep
from collections.abc import Awaitable, Callable
import aiomqtt

logger = logging.getLogger(__name__)


async def consume(host: str, port: int, username: str | None, password: str | None,
                  tls: bool, identifier: str, ingest: Callable[[str, bytes], Awaitable[object]]) -> None:
    delay = 1
    while True:
        try:
            async with aiomqtt.Client(hostname=host, port=port, username=username, password=password,
                                      identifier=identifier, clean_session=False,
                                      tls_context=ssl.create_default_context() if tls else None) as client:
                await client.subscribe("application/+/device/+/event/up", qos=1)
                logger.info("Suscripción MQTT activa")
                delay = 1
                async for message in client.messages:
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
        except aiomqtt.MqttError:
            logger.warning("MQTT desconectado; reintentando en %s s", delay)
            await sleep(delay)
            delay = min(delay * 2, 30)
