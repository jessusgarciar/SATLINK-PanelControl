"""Coordina contexto, consulta y commit sin mezclar predicción y mediciones."""
import asyncio
import logging
import math
import re
from datetime import datetime, timezone
from app.application.ports.prediction import PredictionProvider, PredictionPublisher, PredictionStore
from app.domain.entities.prediction import PredictionInvalid, PredictionTimeout, PredictionUnavailable
from app.domain.entities.telemetry import JsonObject

logger = logging.getLogger(__name__)
RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not RFC3339.fullmatch(value):
        raise PredictionInvalid("Fecha RFC3339 con zona requerida")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise PredictionInvalid("Fecha inválida") from exc


def number(value: object, minimum: float, maximum: float) -> float:
    if (isinstance(value, bool) or not isinstance(value, (float, int)) or
            not math.isfinite(value) or not minimum <= value <= maximum):
        raise PredictionInvalid("Número del predictor inválido")
    return float(value)


def point(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise PredictionInvalid("Punto de trayectoria inválido")
    longitude = number(value.get("longitude"), -180, 360)
    return {"latitude": number(value.get("latitude"), -90, 90),
            "longitude": (longitude + 180) % 360 - 180,
            "altitudeM": number(value.get("altitude"), -500, 65534),
            "time": timestamp(value.get("datetime")).isoformat()}


def validate_effective_request(raw: JsonObject, expected: JsonObject) -> None:
    """Comprueba campos efectivos presentes sin exigir metadatos opcionales."""
    candidates = []
    if isinstance(raw.get("request"), dict):
        candidates.append(raw["request"])
    metadata = raw.get("metadata")
    if isinstance(metadata, dict):
        candidates.append(metadata)
        if isinstance(metadata.get("request"), dict):
            candidates.append(metadata["request"])
    for candidate in candidates:
        for key, wanted in expected.items():
            if key not in candidate:
                continue
            actual = candidate[key]
            if key == "profile":
                matches = actual == wanted
            elif key == "launch_datetime":
                matches = abs((timestamp(actual) - timestamp(wanted)).total_seconds()) <= 1
            elif key == "launch_longitude":
                value = number(actual, -180, 360)
                matches = abs(((value - wanted + 180) % 360) - 180) <= 0.0001
            else:
                value = number(actual, -500, 65534)
                tolerance = 0.0001 if key == "launch_latitude" else 0.000001
                matches = abs(value - wanted) <= tolerance
            if not matches:
                raise PredictionInvalid("Los parámetros efectivos del predictor no corresponden a la solicitud")


def normalize_prediction(raw: JsonObject, mission_id: str, attempt_id: str,
                         parameters: JsonObject, context: JsonObject,
                         generated_at: datetime, *, expected_request: JsonObject | None = None) -> JsonObject:
    expected = {"profile": "standard_profile", "launch_latitude": context["origin"]["latitude"],
                "launch_longitude": context["origin"]["longitude"] % 360,
                "launch_altitude": context["origin"]["altitudeM"], "launch_datetime": context["originAt"],
                "ascent_rate": parameters["ascentRateMs"], "descent_rate": parameters["descentRateMs"]}
    if context["mode"] == "planned":
        expected["burst_altitude"] = context["origin"]["altitudeM"] + parameters["targetRelativeAltitudeM"]
    validate_effective_request(raw, expected if expected_request is None else expected_request)
    stages = raw.get("prediction")
    if (not isinstance(stages, list) or len(stages) != 2 or
            not all(isinstance(stage, dict) for stage in stages) or
            [stage.get("stage") for stage in stages] != ["ascent", "descent"]):
        raise PredictionInvalid("Se requieren etapas completas de ascenso y descenso")
    paths: list[list[JsonObject]] = []
    for stage in stages:
        trajectory = stage.get("trajectory")
        if not isinstance(trajectory, list) or not 2 <= len(trajectory) <= 10000:
            raise PredictionInvalid("Trayectoria vacía, incompleta o demasiado grande")
        points = [point(p) for p in trajectory]
        if any(timestamp(b["time"]) <= timestamp(a["time"]) for a, b in zip(points, points[1:])):
            raise PredictionInvalid("Trayectoria no ordenada")
        paths.append(points)
    ascent, descent = paths
    if (any(b["altitudeM"] < a["altitudeM"] - 1 for a, b in zip(ascent, ascent[1:])) or
            any(b["altitudeM"] > a["altitudeM"] + 1 for a, b in zip(descent, descent[1:]))):
        raise PredictionInvalid("El perfil no mantiene ascenso y descenso coherentes")
    release, landing = ascent[-1], descent[-1]
    origin = context["origin"]
    if (abs(ascent[0]["latitude"] - origin["latitude"]) > 0.0001 or
            abs(((ascent[0]["longitude"] - origin["longitude"] + 180) % 360) - 180) > 0.0001 or
            abs(ascent[0]["altitudeM"] - origin["altitudeM"]) > 1):
        raise PredictionInvalid("El resultado no corresponde al origen solicitado")
    if (abs(descent[0]["latitude"] - release["latitude"]) > 0.0001 or
            abs(((descent[0]["longitude"] - release["longitude"] + 180) % 360) - 180) > 0.0001 or
            abs(descent[0]["altitudeM"] - release["altitudeM"]) > 1):
        raise PredictionInvalid("La transición del resultado es discontinua")
    if context["mode"] == "planned":
        target = origin["altitudeM"] + parameters["targetRelativeAltitudeM"]
        if (abs(release["altitudeM"] - target) > 10 or
                any(p["altitudeM"] > target + 10 for p in ascent + descent)):
            raise PredictionInvalid("El resultado no alcanza el objetivo de transición solicitado")
    if timestamp(descent[0]["time"]) < timestamp(release["time"]):
        raise PredictionInvalid("Etapas del predictor se solapan")
    if abs((timestamp(ascent[0]["time"]) - timestamp(context["originAt"])).total_seconds()) > 1:
        raise PredictionInvalid("La trayectoria no comienza en la fecha de origen solicitada")
    if (release["altitudeM"] <= ascent[0]["altitudeM"] or
            landing["altitudeM"] >= release["altitudeM"]):
        raise PredictionInvalid("Perfil estándar incompatible con el resultado")
    trajectory = ascent + (descent[1:] if descent[0] == release else descent)
    if len(trajectory) > 10000:
        raise PredictionInvalid("Trayectoria demasiado grande")
    metadata = raw.get("request")
    dataset_value = metadata.get("dataset") if isinstance(metadata, dict) else None
    if dataset_value is not None and (isinstance(dataset_value, bool) or
                                      not isinstance(dataset_value, (str, int))):
        raise PredictionInvalid("Dataset meteorológico inválido")
    dataset = None if dataset_value is None else str(dataset_value)
    weather_at = None
    if dataset is not None and RFC3339.fullmatch(dataset):
        weather_at = timestamp(dataset).isoformat()
    if dataset is not None and re.fullmatch(r"\d{10}", dataset):
        try:
            weather_at = datetime.strptime(dataset, "%Y%m%d%H").replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    return {"id": attempt_id, "missionId": mission_id, "generatedAt": generated_at.isoformat(),
            "weatherAt": weather_at, "source": "tawhiri", "parameters": parameters,
            "context": {**context, "dataset": dataset}, "trajectory": trajectory,
            "release": release, "landing": landing}


class PredictMission:
    def __init__(self, store: PredictionStore, provider: PredictionProvider,
                 publisher: PredictionPublisher) -> None:
        self.store, self.provider, self.publisher = store, provider, publisher

    async def execute(self, mission_id: str, parameters: JsonObject,
                      references: JsonObject) -> JsonObject:
        now = datetime.now(timezone.utc)
        current = await self.store.prediction_context(mission_id)
        mission, latest = current["mission"], current["telemetry"]
        if mission.get("phase") in ("descending", "landed"):
            raise PredictionInvalid("El perfil estándar no actualiza descenso ni aterrizaje")
        if references.get("launchAltitudeReference", "unknown") != "MSL":
            raise PredictionInvalid("Declara la altitud de lanzamiento como MSL antes de predecir")
        mode = parameters["mode"]
        if mode == "planned":
            origin, origin_at, telemetry_id = mission["launch"], timestamp(parameters["launchDatetime"]), None
            if origin_at < now:
                raise PredictionInvalid("El lanzamiento planificado debe ser futuro")
        else:
            if references.get("gpsAltitudeReference", "unknown") != "MSL":
                raise PredictionInvalid("La actualización GPS requiere datum MSL confirmado")
            if mission.get("phase") in ("descending", "landed"):
                raise PredictionInvalid("El perfil estándar no actualiza descenso ni aterrizaje")
            if latest is None or any(latest.get(k) is None for k in ("latitude", "longitude", "altitudeGpsM")):
                raise PredictionInvalid("Se requiere una muestra GPS válida")
            origin_at = timestamp(latest["receivedAt"])
            age = (now - origin_at).total_seconds()
            if age < -5 or age > mission["staleAfterSeconds"]:
                raise PredictionInvalid("La muestra GPS no es reciente")
            origin = {"latitude": latest["latitude"], "longitude": latest["longitude"],
                      "altitudeM": latest["altitudeGpsM"]}
            telemetry_id = latest["id"]
        target = mission["launch"]["altitudeM"] + parameters["targetRelativeAltitudeM"]
        if target <= origin["altitudeM"]:
            raise PredictionInvalid("La altitud de transición debe superar la altitud de origen")
        context = {"mode": mode, "origin": origin, "originAt": origin_at.isoformat(),
                   "telemetryId": telemetry_id, "dataset": None, "altitudeReference": "MSL"}
        wire = {"profile": "standard_profile", "launch_latitude": origin["latitude"],
                "launch_longitude": origin["longitude"] % 360, "launch_altitude": origin["altitudeM"],
                "launch_datetime": origin_at.isoformat(), "ascent_rate": parameters["ascentRateMs"],
                "descent_rate": parameters["descentRateMs"], "burst_altitude": target}
        attempt_id = await self.store.reserve_prediction(mission_id, wire, now)
        raw = None
        try:
            async with asyncio.timeout(10):
                raw = await self.provider.predict(wire)
                result = normalize_prediction(raw, mission_id, attempt_id, parameters,
                                              context, datetime.now(timezone.utc), expected_request=wire)
                if (abs(result["release"]["altitudeM"] - target) > 10 or
                        any(p["altitudeM"] > target + 10 for p in result["trajectory"])):
                    raise PredictionInvalid("El predictor no alcanzó el objetivo solicitado")
        except (TimeoutError, PredictionTimeout) as exc:
            await self.store.fail_prediction(attempt_id, "timeout", raw)
            raise PredictionTimeout("Tawhiri agotó el límite total de 10 segundos") from exc
        except asyncio.CancelledError:
            await asyncio.shield(self.store.fail_prediction(attempt_id, "cancelled", raw))
            raise
        except Exception as exc:
            await self.store.fail_prediction(attempt_id, "invalid_response" if isinstance(exc, PredictionInvalid) else "upstream_failure", raw)
            raise PredictionUnavailable("La consulta Tawhiri falló; se conserva la predicción anterior") from exc
        await self.store.complete_prediction(attempt_id, raw, result)
        try:
            await self.publisher.publish_prediction(mission_id, result)
        except Exception:
            logger.exception("Predicción guardada; falló su publicación WebSocket")
        return result
