import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.predict import PredictMission
from app.domain.entities.prediction import PredictionTimeout, PredictionUnavailable


def context_and_parameters():
    start = datetime.now(timezone.utc) + timedelta(hours=1)
    current = {"mission": {"phase": "unknown", "launch": {"latitude": 21.0, "longitude": -102.0, "altitudeM": 1870.0},
                            "staleAfterSeconds": 180}, "telemetry": None}
    parameters = {"mode": "planned", "launchDatetime": start.isoformat(), "targetRelativeAltitudeM": 15000,
                  "ascentRateMs": 5, "descentRateMs": 6.5}
    return current, parameters


@pytest.mark.parametrize("failure,expected,reason", [(PredictionTimeout("timeout"), PredictionTimeout, "timeout"),
                                                     (PredictionUnavailable("offline"), PredictionUnavailable, "upstream_failure")])
async def test_provider_failure_records_attempt_without_completing_or_publishing(failure, expected, reason):
    store, provider, publisher = AsyncMock(), AsyncMock(), AsyncMock()
    current, parameters = context_and_parameters()
    store.prediction_context.return_value = current
    store.reserve_prediction.return_value = "attempt-1"
    provider.predict.side_effect = failure
    with pytest.raises(expected):
        await PredictMission(store, provider, publisher).execute("test-flight", parameters, {"launchAltitudeReference": "MSL"})
    store.fail_prediction.assert_awaited_once_with("attempt-1", reason, None)
    store.complete_prediction.assert_not_awaited()
    publisher.publish_prediction.assert_not_awaited()


async def test_cancelled_prediction_records_failure_without_publishing():
    entered = asyncio.Event()
    store, provider, publisher = AsyncMock(), AsyncMock(), AsyncMock()
    current, parameters = context_and_parameters()
    store.prediction_context.return_value = current
    store.reserve_prediction.return_value = "attempt-1"
    async def pending(request):
        entered.set()
        await asyncio.Event().wait()
    provider.predict.side_effect = pending
    task = asyncio.create_task(PredictMission(store, provider, publisher).execute(
        "test-flight", parameters, {"launchAltitudeReference": "MSL"}))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    store.fail_prediction.assert_awaited_once_with("attempt-1", "cancelled", None)
    store.complete_prediction.assert_not_awaited()
    publisher.publish_prediction.assert_not_awaited()
