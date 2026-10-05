"""Consulta externa; la aplicación valida y persiste el resultado completo."""
import json
import httpx
from app.domain.entities.telemetry import JsonObject
from app.domain.entities.prediction import PredictionTimeout, PredictionUnavailable


class TawhiriProvider:
    def __init__(self, url: str, client: httpx.AsyncClient | None = None) -> None:
        self.url = url
        self.owned = client is None
        self.client = client if client is not None else httpx.AsyncClient(
            timeout=httpx.Timeout(9.0, connect=3.0), follow_redirects=False)

    async def predict(self, request: JsonObject) -> JsonObject:
        try:
            async with self.client.stream("GET", self.url, params=request,
                                          headers={"Accept": "application/json"}) as response:
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
            raise PredictionTimeout("Tawhiri agotó el tiempo de espera") from exc
        except (httpx.HTTPError, ValueError, UnicodeError) as exc:
            raise PredictionUnavailable("No se pudo consultar Tawhiri") from exc

    async def close(self) -> None:
        if self.owned:
            await self.client.aclose()
