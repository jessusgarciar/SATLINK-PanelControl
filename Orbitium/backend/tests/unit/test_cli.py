import json

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
