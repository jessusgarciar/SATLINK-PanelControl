from anyio import CancelScope
from starlette.responses import StreamingResponse
from starlette.types import Scope, Receive, Send
from app.application.use_cases.query_telemetry import CsvExport


class CsvStreamingResponse(StreamingResponse):
    """Libera el cursor incluso si el cliente se desconecta antes del primer bloque."""
    def __init__(self, export: CsvExport) -> None:
        self.export = export
        super().__init__(export.chunks(), media_type="text/csv; charset=utf-8",
                         headers={"Content-Disposition": 'attachment; filename="satlink-telemetry.csv"',
                                  "Cache-Control": "no-store"})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            with CancelScope(shield=True):
                await self.export.aclose()
