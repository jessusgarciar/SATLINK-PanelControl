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
        for queue in tuple(self.clients.get(mission_id, ())):
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
            else:
                queue.put_nowait({"type": "telemetry", "data": telemetry})
