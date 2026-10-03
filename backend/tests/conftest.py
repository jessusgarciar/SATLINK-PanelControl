import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from app.infrastructure.database.store import PostgresStore
from app.presentation.schemas.api import MissionConfig


def pytest_asyncio_loop_factories() -> dict:
    return {"selector": asyncio.SelectorEventLoop} if sys.platform == "win32" else {"default": asyncio.new_event_loop}


@pytest.fixture
def mission_config() -> dict:
    return MissionConfig.model_validate({
        "id": "test-flight", "name": "Misión SINTÉTICA de pruebas", "source": "test-chirpstack",
        "applicationId": "test-app", "deviceEui": "0102030405060708",
        "launch": {"latitude": 21.0, "longitude": -102.0, "altitudeM": 1870.0},
        "launchLabel": "Origen SINTÉTICO", "nominalAscentMs": 5.0, "nominalDescentMs": 6.5,
        "watchdogSeconds": 3600, "staleAfterSeconds": 180,
    }).model_dump(mode="json")


@pytest.fixture
def make_uplink():
    def make(binary: bytes | None = None, **changes) -> tuple[str, bytes]:
        event = {
            "deduplicationId": str(uuid4()), "time": "2026-10-02T12:00:00Z",
            "deviceInfo": {"applicationId": "test-app", "devEui": "0102030405060708"},
            "fCnt": 1, "fPort": 10,
            "data": base64.b64encode(binary or bytes.fromhex("04000000000000000000000001cc000a341fdb")).decode(),
            "rxInfo": [{"gatewayId": "weak", "snr": 2, "rssi": -70},
                       {"gatewayId": "strong", "snr": 6, "rssi": -100}],
        }
        event.update(changes)
        return "application/test-app/device/0102030405060708/event/up", json.dumps(event).encode()
    return make


@pytest.fixture
def db_url() -> str:
    value = os.getenv("SATLINK_TEST_DATABASE_URL")
    if not value:
        pytest.skip("SATLINK_TEST_DATABASE_URL no configurada; integración PostgreSQL pendiente")
    url = make_url(value)
    if url.drivername != "postgresql+psycopg" or not (url.database or "").endswith("_test"):
        pytest.fail("Pruebas requieren PostgreSQL dedicado con nombre terminado en _test")
    return value


@pytest.fixture
async def store(db_url, mission_config):
    repository = PostgresStore(db_url)
    def migrate(connection):
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    async with repository.engine.begin() as connection:
        await connection.run_sync(migrate)
        await connection.execute(text("TRUNCATE telemetry, received_events, missions"))
    await repository.initialize_mission(mission_config)
    yield repository
    await repository.close()
