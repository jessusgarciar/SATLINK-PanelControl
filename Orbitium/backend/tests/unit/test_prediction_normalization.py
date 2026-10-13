from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.application.use_cases.predict import normalize_prediction
from app.domain.entities.prediction import PredictionInvalid


GENERATED = datetime(2026, 10, 3, 18, tzinfo=timezone.utc)
PARAMETERS = {"mode": "planned", "launchDatetime": "2026-10-04T12:00:00Z",
              "targetRelativeAltitudeM": 15000.0, "ascentRateMs": 5.0, "descentRateMs": 6.5}
CONTEXT = {"mode": "planned", "origin": {"latitude": 21.0, "longitude": -102.0, "altitudeM": 1870.0},
           "originAt": PARAMETERS["launchDatetime"], "telemetryId": None, "dataset": None,
           "altitudeReference": "MSL"}


def raw_prediction():
    def point(date, altitude, latitude, longitude):
        return {"datetime": date, "altitude": altitude, "latitude": latitude, "longitude": longitude}
    transition = point("2026-10-04T12:50:00Z", 16870, 21.1, 258.1)
    return {"request": {"dataset": "2026100318"}, "prediction": [
        {"stage": "ascent", "trajectory": [point("2026-10-04T12:00:00Z", 1870, 21, 258), transition]},
        {"stage": "descent", "trajectory": [deepcopy(transition), point("2026-10-04T13:30:00Z", 1600, 21.2, 258.2)]}]}


def normalize(raw):
    return normalize_prediction(raw, "test-flight", "attempt-1", deepcopy(PARAMETERS), deepcopy(CONTEXT), GENERATED)


def test_normalization_separates_prediction_context_and_converts_longitudes_and_weather():
    raw = raw_prediction()
    before = deepcopy(raw)
    result = normalize(raw)
    assert raw == before
    assert result["source"] == "tawhiri"
    assert result["parameters"] == PARAMETERS
    assert result["context"]["dataset"] == "2026100318"
    assert datetime.fromisoformat(result["weatherAt"].replace("Z", "+00:00")) == GENERATED
    assert result["landing"]["longitude"] == pytest.approx(-101.8)
    assert result["release"]["altitudeM"] == 16870
    assert len(result["trajectory"]) == 3


@pytest.mark.parametrize("dataset", [None, "unknown-cycle"])
def test_missing_or_unparseable_dataset_never_invents_weather_time(dataset):
    raw = raw_prediction()
    raw["request"]["dataset"] = dataset
    assert normalize(raw)["weatherAt"] is None


def test_standard_profile_rejects_a_transition_for_a_different_requested_target():
    raw = raw_prediction()
    for stage in raw["prediction"]:
        stage["trajectory"][-1 if stage["stage"] == "ascent" else 0]["altitude"] = 10000
    with pytest.raises(PredictionInvalid):
        normalize(raw)


def test_standard_profile_accepts_small_integration_undershoot_without_claiming_physical_accuracy():
    # The 10 m allowance validates numerical integration, not flight precision.
    # Observed real provider response: target 16870 m, ascent ends at 16868 m.
    raw = raw_prediction()
    for stage in raw["prediction"]:
        stage["trajectory"][-1 if stage["stage"] == "ascent" else 0]["altitude"] = 16868
    result = normalize(raw)
    assert result["release"]["altitudeM"] == 16868
    assert result["parameters"]["targetRelativeAltitudeM"] == 15000


def test_trajectory_start_must_match_requested_origin_time_within_one_second():
    raw = raw_prediction()
    raw["prediction"][0]["trajectory"][0]["datetime"] = "2026-10-04T12:00:02Z"
    with pytest.raises(PredictionInvalid):
        normalize(raw)


@pytest.mark.parametrize("case", ["missing_stage", "reversed_stages", "empty_ascent", "invalid_latitude",
                                  "nonfinite_altitude", "naive_date", "backwards_time", "origin_mismatch",
                                  "transition_mismatch", "exceeds_target", "ascending_falls", "descending_rises",
                                  "ascent_internal_fall", "descent_internal_rise"])
def test_incomplete_or_inconsistent_trajectory_is_rejected(case):
    raw = raw_prediction()
    ascent, descent = raw["prediction"]
    if case == "missing_stage": raw["prediction"].pop()
    elif case == "reversed_stages": raw["prediction"].reverse()
    elif case == "empty_ascent": ascent["trajectory"] = []
    elif case == "invalid_latitude": descent["trajectory"][-1]["latitude"] = 91
    elif case == "nonfinite_altitude": descent["trajectory"][-1]["altitude"] = float("nan")
    elif case == "naive_date": ascent["trajectory"][0]["datetime"] = "2026-10-04T12:00:00"
    elif case == "backwards_time": descent["trajectory"][-1]["datetime"] = "2026-10-04T12:40:00Z"
    elif case == "origin_mismatch": ascent["trajectory"][0]["altitude"] = 3000
    elif case == "transition_mismatch": descent["trajectory"][0]["latitude"] = 22
    elif case == "exceeds_target": ascent["trajectory"][-1]["altitude"] = 18000
    elif case == "ascending_falls": ascent["trajectory"][-1]["altitude"] = 1000
    elif case == "descending_rises": descent["trajectory"][-1]["altitude"] = 17000
    elif case == "ascent_internal_fall":
        ascent["trajectory"].insert(1, {"datetime": "2026-10-04T12:10:00Z", "altitude": 1000,
                                         "latitude": 21.02, "longitude": 258.02})
    elif case == "descent_internal_rise":
        descent["trajectory"].insert(1, {"datetime": "2026-10-04T13:00:00Z", "altitude": 17000,
                                          "latitude": 21.12, "longitude": 258.12})
    with pytest.raises(PredictionInvalid):
        normalize(raw)
