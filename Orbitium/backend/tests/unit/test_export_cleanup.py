import asyncio
from unittest.mock import AsyncMock

import pytest
from starlette.requests import ClientDisconnect

from app.application.use_cases.query_telemetry import CsvExport
from app.infrastructure.database.store import DatabaseExport
from app.presentation.api.streaming import CsvStreamingResponse


async def test_database_export_closes_cursor_and_session_when_iteration_is_cancelled():
    session = AsyncMock()

    class Result:
        close = AsyncMock()

        def __aiter__(self):
            async def stream():
                raise asyncio.CancelledError
                yield
            return stream()

    result = Result()
    archive = DatabaseExport(session, result)
    with pytest.raises(asyncio.CancelledError):
        async for _ in archive:
            pass
    result.close.assert_awaited_once()
    session.close.assert_awaited_once()
    await archive.aclose()
    result.close.assert_awaited_once()
    session.close.assert_awaited_once()


async def test_database_export_also_closes_session_when_cursor_cleanup_fails():
    session, result = AsyncMock(), AsyncMock()
    result.close.side_effect = RuntimeError("synthetic cursor close failure")
    archive = DatabaseExport(session, result)
    with pytest.raises(RuntimeError, match="cursor close"):
        await archive.aclose()
    session.close.assert_awaited_once()


@pytest.mark.parametrize("fail_before_header", [True, False])
async def test_csv_disconnect_before_or_after_header_releases_archive(fail_before_header):
    class Archive:
        def __init__(self):
            self.closed = False
            self.iterated = False

        def __aiter__(self):
            async def stream():
                self.iterated = True
                yield {"telemetry": {"id": "synthetic"}, "source": "test", "raw_json": {}}
            return stream()

        async def aclose(self):
            self.closed = True

    archive = Archive()
    response = CsvStreamingResponse(CsvExport(archive))
    scope = {"type": "http", "method": "GET", "headers": [], "asgi": {"spec_version": "2.4"}}
    sent = []

    async def send(message):
        sent.append(message)
        if fail_before_header or message["type"] == "http.response.body":
            raise OSError("synthetic client disconnect")

    async def receive():
        return {"type": "http.disconnect"}

    with pytest.raises(ClientDisconnect):
        await response(scope, receive, send)
    assert archive.closed is True
    assert archive.iterated is False
    assert sent[0]["type"] == "http.response.start"
