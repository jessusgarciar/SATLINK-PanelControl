"""Origen supuesto de la demostración visual; no configura la estación física."""
DEMO_MISSION = {
    "id": "satlink-demo", "name": "SATLINK · Misión de demostración",
    "source": "frontend-demo", "applicationId": "frontend-demo",
    "deviceEui": "0000000000000000",
    "launch": {"latitude": 21.88535, "longitude": -102.29167, "altitudeM": 1870.0},
    "launchLabel": "AGS · Origen de ejemplo", "targetRelativeAltitudeM": 15000.0,
    "nominalAscentMs": 5.0, "nominalDescentMs": 6.5,
    "watchdogSeconds": 3300, "staleAfterSeconds": 15, "region": "US915",
}
