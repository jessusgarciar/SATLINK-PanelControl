import json
import pytest
from app.infrastructure.mqtt.picaro import decode_payload
from app.presentation.schemas.uplink import ChirpStackDecoder, utc_time

REFERENCE = bytes.fromhex("04000000000000000000000001cc000a341fdb")


def test_documented_vector_and_absent_fields():
    t = decode_payload(REFERENCE, 10)
    assert (t["temperatureC"], t["pressureHpa"], t["batteryV"]) == (26.12, 815.5, 0.46)
    assert t["latitude"] is t["longitude"] is t["altitudeGpsM"] is t["humidityPct"] is None
    assert t["metadata"]["usbPowered"] is True


def test_signed_values_zero_temperature_and_battery_sentinel():
    # -1 grado, -2 grados, -100m; 4000mV; 255%; 0°C; 1000hPa.
    t = decode_payload(bytes.fromhex("21fff0bdc0ffe17b80ff9c080fa0ff00002710"), 10)
    assert (t["latitude"], t["longitude"], t["altitudeGpsM"]) == (-1, -2, -100)
    assert t["temperatureC"] == 0
    assert t["batteryV"] == 4
    assert t["pressureHpa"] == 1000
    assert t["metadata"]["batteryPct"] is None


def test_negative_temperature_and_pressure_255_is_real():
    t = decode_payload(bytes.fromhex("0100000000000000000000000fa064fc1809f6"), 10)
    assert t["temperatureC"] == -10
    assert t["pressureHpa"] == 255
    assert (t["latitude"], t["longitude"]) == (0, 0)


@pytest.mark.parametrize("payload,port", [(REFERENCE[:-1], 10), (REFERENCE+b'\0', 10), (b'', 10), (REFERENCE, 1), (REFERENCE, True)])
def test_wrong_layout_is_rejected(payload, port):
    with pytest.raises(ValueError):
        decode_payload(payload, port)


def test_radio_values_come_from_same_gateway(make_uplink):
    t = ChirpStackDecoder(decode_payload).decode(*make_uplink(), "source")
    assert (t.measurements["snrDb"], t.measurements["rssiDbm"]) == (6, -100)
    assert t.metadata["selectedGatewayId"] == "strong"
    assert len(t.raw_event["rxInfo"]) == 2


@pytest.mark.parametrize("changes", [{"data":"?"}, {"fPort":True}, {"fCnt":-1}, {"deduplicationId":"bad"}, {"time":"2026-10-02T00:00:00"}, {"fCnt":2**32}])
def test_invalid_envelope(make_uplink, changes):
    with pytest.raises(ValueError):
        ChirpStackDecoder(decode_payload).decode(*make_uplink(**changes), "source")


def test_topic_mismatch_and_nonfinite_json(make_uplink):
    topic, raw = make_uplink()
    decoder = ChirpStackDecoder(decode_payload)
    with pytest.raises(ValueError):
        decoder.decode(topic.replace("test-app", "another"), raw, "source")
    for bad in (b'{"x":NaN}', b'{"x":1e999}', b'not json', b'[]',
                b'{"x":"\\u0000"}', b'{"x":"\\ud800"}', b'{"x":1,"x":2}'):
        with pytest.raises(ValueError):
            decoder.decode(topic, bad, "source")


def test_omitted_proto_counter_is_zero(make_uplink):
    topic, raw = make_uplink()
    data = json.loads(raw)
    del data["fCnt"]
    assert ChirpStackDecoder(decode_payload).decode(topic, json.dumps(data).encode(), "source").frame_counter == 0
    assert utc_time("2026-10-02T06:00:00-06:00").hour == 12
