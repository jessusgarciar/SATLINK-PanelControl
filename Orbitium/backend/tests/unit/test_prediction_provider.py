"""Adapter behavior with HTTPX transport doubles; no external requests."""
import httpx
import pytest

from app.domain.entities.prediction import PredictionTimeout, PredictionUnavailable
from app.infrastructure.prediction.tawhiri import TawhiriProvider


REQUEST = {"launch_latitude": 21.0, "launch_longitude": 258.0, "launch_altitude": 1870.0,
           "launch_datetime": "2026-10-05T12:00:00Z", "burst_altitude": 16870.0,
           "ascent_rate": 5.0, "descent_rate": 6.5, "profile": "standard_profile"}


async def test_provider_queries_configured_endpoint_without_demo_inputs_and_preserves_raw_json():
    seen = []
    raw = {"request": {**REQUEST, "dataset": "2026100318"}, "prediction": []}
    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=raw)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = TawhiriProvider("https://predictor.test/tawhiri", client)
        assert await provider.predict(REQUEST) == raw
        assert seen[0].method == "GET"
        assert seen[0].url.host == "predictor.test"
        assert dict(seen[0].url.params) == {key: str(value) for key, value in REQUEST.items()}
        assert seen[0].headers["Accept"] == "application/json"
        await provider.close()
        assert client.is_closed is False


@pytest.mark.parametrize("response", [httpx.Response(503, json={"error": "unavailable"}),
                                       httpx.Response(400, json={"error": "bad profile"}),
                                       httpx.Response(302, headers={"Location": "https://elsewhere.test"}),
                                       httpx.Response(200, text="<html/>", headers={"Content-Type": "text/html"}),
                                       httpx.Response(200, content=b"{broken", headers={"Content-Type": "application/json"}),
                                       httpx.Response(200, json=[]),
                                       httpx.Response(200, content=b" " * (8 * 1024 * 1024 + 1),
                                                      headers={"Content-Type": "application/json"})])
async def test_provider_rejects_upstream_errors_redirects_non_json_and_oversized_response(response):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
        with pytest.raises(PredictionUnavailable):
            await TawhiriProvider("https://predictor.test/tawhiri", client).predict(REQUEST)


@pytest.mark.parametrize("exception,expected", [(httpx.ReadTimeout("synthetic timeout"), PredictionTimeout),
                                                (httpx.ConnectError("synthetic offline"), PredictionUnavailable)])
async def test_provider_classifies_network_failure_without_automatic_retry(exception, expected):
    calls = 0
    def handler(request):
        nonlocal calls
        calls += 1
        raise exception
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(expected):
            await TawhiriProvider("https://predictor.test/tawhiri", client).predict(REQUEST)
    assert calls == 1
