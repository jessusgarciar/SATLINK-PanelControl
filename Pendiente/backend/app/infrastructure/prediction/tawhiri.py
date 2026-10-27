"""Consulta externa; la aplicación valida y persiste el resultado completo."""
import json
import logging
from time import perf_counter
import httpx
from app.domain.entities.telemetry import JsonObject
from app.domain.entities.prediction import PredictionTimeout, PredictionUnavailable


logger = logging.getLogger(__name__)


class TawhiriProvider:
    def __init__(self, url: str, client: httpx.AsyncClient | None = None) -> None:
        self.url = url
        self.owned = client is None
        self.client = client if client is not None else httpx.AsyncClient(
            timeout=httpx.Timeout(25.0, connect=5.0, write=5.0, pool=5.0), follow_redirects=False)

    async def predict(self, request: JsonObject) -> JsonObject:
        started = perf_counter()
        try:
            async with self.client.stream("GET", self.url, params=request,
                                          headers={"Accept": "application/json"}) as response:
                logger.info("Tawhiri response: status=%s elapsed=%.2fs", response.status_code, perf_counter() - started)
                response.raise_for_status()
                if "application/json" not in response.headers.get("content-type", ""):
                    raise PredictionUnavailable("Tawhiri no devolvió JSON")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 8 * 1024 * 1024:
                        raise PredictionUnavailable("Respuesta Tawhiri demasiado grande")
            value = json.loads(data)
            if not isinstance(value, dict):
                raise PredictionUnavailable("Respuesta Tawhiri incompleta")
            return value
        except httpx.TimeoutException as exc:
            phase = "conexión" if isinstance(exc, httpx.ConnectTimeout) else "lectura" if isinstance(exc, httpx.ReadTimeout) else "comunicación"
            logger.warning("Tawhiri timeout: phase=%s elapsed=%.2fs", phase, perf_counter() - started)
            raise PredictionTimeout(f"Se agotó la espera de {phase} con Tawhiri. Se conserva la predicción anterior.") from exc
        except httpx.HTTPStatusError as exc:
            code = exc.response.status_code
            if code == 429:
                message = "Tawhiri limitó las consultas (HTTP 429). Espera antes de volver a calcular."
            elif code == 402:
                message = "El servicio de predicción respondió HTTP 402. Revisa el acceso al proveedor."
            else:
                message = f"Tawhiri respondió HTTP {code}. Intenta más tarde."
            raise PredictionUnavailable(message) from exc
        except (httpx.HTTPError, ValueError, UnicodeError) as exc:
            raise PredictionUnavailable("No se pudo consultar Tawhiri") from exc

    async def close(self) -> None:
        if self.owned:
            await self.client.aclose()
