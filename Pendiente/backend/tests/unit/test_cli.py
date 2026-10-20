import asyncio
import json
import sys

import pytest

from app.bootstrap.cli import configured_mqtt_topic
from app.bootstrap.config import Settings
from app.bootstrap.app import create_app


def test_live_mqtt_topic_is_derived_from_validated_mission(tmp_path, mission_config):
    mission_path = tmp_path / "mission.local.json"
    mission_path.write_text(json.dumps(mission_config), encoding="utf-8")
    settings = Settings(database_url="postgresql+psycopg://test@127.0.0.1/test",
                        source="test-chirpstack", mqtt_enabled=True, mqtt_host="test-broker")

    assert configured_mqtt_topic(settings, mission_path) == (
        "application/test-app/device/0102030405060708/event/up")


def test_live_mqtt_topic_rejects_mission_with_different_source(tmp_path, mission_config):
    mission_path = tmp_path / "mission.local.json"
    mission_path.write_text(json.dumps({**mission_config, "source": "another-source"}), encoding="utf-8")
    settings = Settings(database_url="postgresql+psycopg://test@127.0.0.1/test",
                        source="test-chirpstack", mqtt_enabled=True, mqtt_host="test-broker")

    with pytest.raises(ValueError, match="SATLINK_CHIRPSTACK_SOURCE"):
        configured_mqtt_topic(settings, mission_path)


def test_disabled_mqtt_does_not_read_mission_file():
    settings = Settings(database_url="postgresql+psycopg://test@127.0.0.1/test")

    assert configured_mqtt_topic(settings) is None


def test_app_refuses_enabled_mqtt_without_mission_topic():
    settings = Settings(database_url="postgresql+psycopg://test@127.0.0.1/test",
                        mqtt_enabled=True, mqtt_host="test-broker")

    with pytest.raises(ValueError, match="topic MQTT de la misión"):
        create_app(settings)


@pytest.mark.parametrize("outcome,exit_code", [("passed", 0), ("failed", 1), ("cancelled", 130), ("timeout", 1)])
def test_check_live_cli_writes_report_and_safe_exit(monkeypatch, tmp_path, mission_config, outcome, exit_code):
    from app.bootstrap import cli, check_live

    mission = tmp_path / "mission.json"
    mission.write_text(json.dumps(mission_config), encoding="utf-8")
    report = tmp_path / "report.json"
    settings = Settings(database_url="postgresql+psycopg://test@127.0.0.1/test", source=mission_config["source"])
    monkeypatch.setattr(Settings, "from_env", lambda: settings)
    monkeypatch.setattr(sys, "argv", ["satlink", "check-live", "--file", str(mission), "--report", str(report)])

    async def execute(settings, config, samples, timeout, result):
        if outcome == "timeout":
            result.update(checks={"mqttSubscription": True}, mqttEvents=0)
            raise TimeoutError()
        if outcome == "failed":
            raise RuntimeError("secret-password-must-not-appear")
        if outcome == "cancelled":
            # La cancelación de la terminal se simula en run_async más abajo.
            raise asyncio.CancelledError()
        result.update(status="passed", verifiedSamples=samples)

    monkeypatch.setattr(check_live, "check_live", execute)
    if outcome == "cancelled":
        def interrupt(coroutine):
            coroutine.close()
            raise KeyboardInterrupt()
        monkeypatch.setattr(cli, "run_async", interrupt)
    if exit_code:
        with pytest.raises(SystemExit) as exc:
            cli.main()
        assert exc.value.code == exit_code
    else:
        cli.main()
    content = report.read_text(encoding="utf-8")
    assert json.loads(content)["status"] == ("failed" if outcome == "timeout" else outcome)
    if outcome == "timeout":
        assert "no llegaron uplinks nuevos" in json.loads(content)["reason"]
    assert "secret-password" not in content
