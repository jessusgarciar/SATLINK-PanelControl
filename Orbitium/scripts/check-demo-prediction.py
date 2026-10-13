"""Consulta manual de integración con el proveedor real; conserva evidencia local."""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=("planned", "ascending"), default="planned")
args = parser.parse_args()
now = datetime.now(timezone.utc)
body = {"phase": "ascending", "parameters": {
    "mode": args.mode, "targetRelativeAltitudeM": 15000.0, "ascentRateMs": 5.0, "descentRateMs": 6.5,
}, "sample": None}
if args.mode == "planned":
    body["parameters"]["launchDatetime"] = (now + timedelta(hours=1)).isoformat()
else:
    body["sample"] = {"latitude": 21.886286, "longitude": -102.289954,
                      "altitudeM": 2650.0, "time": now.isoformat()}
with httpx.Client(base_url="http://127.0.0.1:5173", timeout=15) as client:
    session = client.get("/api/v1/demo/predictions").raise_for_status().json()
    response = client.post("/api/v1/demo/predictions", json=body,
        headers={"Origin": "http://127.0.0.1:5173", "X-CSRF-Token": session["csrfToken"]})
    response.raise_for_status()
    result = response.json()
    assert result["source"] == "tawhiri" and result["context"]["inputSource"] == "simulated"
    assert result["missionId"] == "satlink-demo"
    latest = client.get("/api/v1/demo/predictions").raise_for_status().json()
    assert latest["prediction"]["id"] == result["id"]
    assert latest["nextAllowedAt"] is not None
    repeated = client.post("/api/v1/demo/predictions", json=body,
        headers={"Origin": "http://127.0.0.1:5173", "X-CSRF-Token": session["csrfToken"]})
    assert repeated.status_code == 429
    path = Path(__file__).resolve().parents[1] / ".local" / "dev-logs" / f"demo-{args.mode}.json"
    path.write_text(json.dumps({"input": body, "result": result}, indent=2), encoding="utf-8")
    print(json.dumps({"source": result["source"], "inputs": result["context"]["inputSource"],
        "mode": args.mode, "points": len(result["trajectory"]), "weatherAt": result["weatherAt"],
        "persisted": True, "cooldown": repeated.status_code, "evidence": str(path)}))
