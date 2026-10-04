import asyncio
from collections import defaultdict
from contextlib import contextmanager
from collections.abc import Iterator
from app.domain.entities.telemetry import JsonObject


class TelemetryHub:
    def __init__(self) -> None:
        self.clients: dict[str, set[asyncio.Queue[JsonObject | None]]] = defaultdict(set)

    @contextmanager
    def subscribe(self, mission_id: str) -> Iterator[asyncio.Queue[JsonObject | None]]:
        queue: asyncio.Queue[JsonObject | None] = asyncio.Queue(maxsize=256)
        self.clients[mission_id].add(queue)
        try:
            yield queue
        finally:
            self.clients[mission_id].discard(queue)
            if not self.clients[mission_id]:
                del self.clients[mission_id]

    async def publish(self, mission_id: str, telemetry: JsonObject) -> None:
        self.send(mission_id, {"type": "telemetry", "data": telemetry})

    def send(self, mission_id: str, message: JsonObject) -> None:
        for queue in tuple(self.clients.get(mission_id, ())):
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
            else:
                queue.put_nowait(message)

    async def publish_ingestion(self, data: JsonObject, mission_ids: set[str] | None = None) -> None:
        for mission_id in tuple(self.clients):
            if mission_ids is None or mission_id in mission_ids:
                self.send(mission_id, {"type": "ingestion", "data": data})
