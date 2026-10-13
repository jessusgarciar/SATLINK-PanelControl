"""Independent planning uses an explicit origin without changing flight state."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from pydantic import TypeAdapter, ValidationError

from app.application.use_cases.predict import PredictMission
from app.presentation.schemas.prediction import PredictionRequest


ADAPTER = TypeAdapter(PredictionRequest)
MISSION_ORIGIN = {"latitude": 21.0, "longitude": -102.0, "altitudeM": 1870.0}
MANUAL_ORIGIN = {"latitude": 21.5, "longitude": -101.5, "altitudeM": 2300.0}


def planned_body(**changes):
    return {"mode": "planned", "launchDatetime": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "targetRelativeAltitudeM": 15000.0, "ascentRateMs": 5.0, "descentRateMs": 6.5, **changes}


def prediction_response(request):
    start = datetime.fromisoformat(request["launch_datetime"].replace("Z", "+00:00"))
    def point(seconds, altitude):
        return {"datetime": (start + timedelta(seconds=seconds)).isoformat(), "altitude": altitude,
                "latitude": request["launch_latitude"], "longitude": request["launch_longitude"]}
    transition = point(3000, request["burst_altitude"])
    return {"request": {**request, "dataset": "2026100700"}, "prediction": [
        {"stage": "ascent", "trajectory": [point(0, request["launch_altitude"]), transition]},
        {"stage": "descent", "trajectory": [deepcopy(transition), point(6000, 0.0)]}]}


def service_doubles():
    current = {"mission": {"phase": "unknown", "launch": deepcopy(MISSION_ORIGIN), "staleAfterSeconds": 180},
               "telemetry": None}
    store, provider, publisher = AsyncMock(), AsyncMock(), AsyncMock()
    store.prediction_context.return_value = current
    store.reserve_prediction.return_value = "manual-attempt"
    provider.predict.side_effect = prediction_response
    return PredictMission(store, provider, publisher), store, provider, publisher, current


@pytest.mark.parametrize("origin", [MANUAL_ORIGIN, {"latitude": 0.0, "longitude": 0.0, "altitudeM": 0.0}])
async def test_manual_planning_uses_explicit_msl_origin_and_preserves_mission(origin):
    service, store, provider, publisher, current = service_doubles()
    before = deepcopy(current)
    body = planned_body(launch=origin, launchAltitudeReference="MSL")
    parameters = ADAPTER.validate_python(body).model_dump(mode="json")
    result = await service.execute("test-flight", parameters, {})
    request = provider.predict.await_args.args[0]
    assert request["launch_latitude"] == origin["latitude"]
    assert request["launch_longitude"] == origin["longitude"] % 360
    assert request["launch_altitude"] == origin["altitudeM"]
    assert request["burst_altitude"] == origin["altitudeM"] + 15000
    assert result["release"]["altitudeM"] == origin["altitudeM"] + 15000
    assert result["context"]["origin"] == origin
    assert result["context"]["telemetryId"] is None
    assert result["context"]["altitudeReference"] == "MSL"
    assert result["parameters"] == body
    assert current == before
    store.complete_prediction.assert_awaited_once()
    publisher.publish_prediction.assert_awaited_once_with("test-flight", result)


async def test_legacy_planning_retains_mission_origin_and_omits_new_optional_parameters():
    service, _, provider, _, current = service_doubles()
    body = planned_body()
    parameters = ADAPTER.validate_python(body).model_dump(mode="json")
    assert parameters == body
    assert "launch" not in parameters and "launchAltitudeReference" not in parameters
    result = await service.execute("test-flight", parameters, {"launchAltitudeReference": "MSL"})
    assert provider.predict.await_args.args[0]["burst_altitude"] == 16870
    assert result["context"]["origin"] == MISSION_ORIGIN
    assert current["mission"]["launch"] == MISSION_ORIGIN


@pytest.mark.parametrize("changes", [
    {"launch": MANUAL_ORIGIN},
    {"launchAltitudeReference": "MSL"},
    {"launch": MANUAL_ORIGIN, "launchAltitudeReference": "unknown"},
    {"launch": MANUAL_ORIGIN, "launchAltitudeReference": "WGS84"},
    {"launch": {**MANUAL_ORIGIN, "latitude": 91}, "launchAltitudeReference": "MSL"},
    {"launch": {**MANUAL_ORIGIN, "longitude": -181}, "launchAltitudeReference": "MSL"},
    {"launch": {**MANUAL_ORIGIN, "altitudeM": -501}, "launchAltitudeReference": "MSL"},
    {"launch": {**MANUAL_ORIGIN, "altitudeM": float("nan")}, "launchAltitudeReference": "MSL"},
])
def test_manual_origin_requires_complete_coordinates_and_explicit_msl_confirmation(changes):
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(planned_body(**changes))


@pytest.mark.parametrize("extras", [{"launch": MANUAL_ORIGIN}, {"launchAltitudeReference": "MSL"},
                                    {"launch": MANUAL_ORIGIN, "launchAltitudeReference": "MSL"}])
def test_ascending_cannot_replace_received_gps_with_manual_planning_origin(extras):
    body = {"mode": "ascending", "targetRelativeAltitudeM": 15000.0, "ascentRateMs": 5.0,
            "descentRateMs": 6.5, **extras}
    with pytest.raises(ValidationError):
        ADAPTER.validate_python(body)
