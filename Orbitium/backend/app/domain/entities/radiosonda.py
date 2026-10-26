"""Estado observado del firmware; no inicia ni controla el watchdog localmente."""
from datetime import datetime
from app.domain.entities.telemetry import JsonObject


def flight_state(previous: JsonObject | None, packet: JsonObject, received_at: datetime) -> JsonObject:
    state = dict(previous or {})
    stamp = received_at.isoformat()
    if state.get("observedAt") and datetime.fromisoformat(state["observedAt"]) > received_at:
        return state
    if packet["fPort"] == 23:
        state.update(enVuelo=packet["enVuelo"], corteEnCurso=packet["corteEnCurso"],
                     cortado=packet["cortado"], lectura=packet["lectura"])
        state["phase"] = ("CORTANDO" if packet["corteEnCurso"] else "CORTADO" if packet["cortado"]
                          else "EN VUELO" if packet["enVuelo"] else "ESPERA")
    elif packet["fPort"] == 31:
        state.update({key: packet[key] for key in ("evento", "motivo", "seq", "intento", "altitudeM",
                     "altitudeSource", "tVueloS", "verticalSpeedMs", "enVuelo")})
        state["eventObservedAt"] = stamp
        state["phase"] = "CORTANDO" if packet["evento"] == "inicio" else "CORTADO" if packet["enVuelo"] else "ESPERA"
        state["cutResult"] = packet["evento"]
    else:
        return state
    state["observedAt"] = stamp
    state["watchdogActive"] = bool(state.get("enVuelo"))
    return state


def command_result(packet: JsonObject, created_at: datetime, received_at: datetime) -> tuple[str, str, JsonObject]:
    if packet["fPort"] == 30:
        rtt = max(0, (received_at - created_at).total_seconds())
        return "executed", "Polo recibido de la sonda; Marco ejecutado.", {
            "rttSeconds": rtt, "rssiDbm": packet["downlinkRssiDbm"], "snrDb": packet["downlinkSnrDb"]}
    outcome = packet["evento"]
    status = "received" if outcome == "inicio" else "executed"
    text = {"inicio": "Firmware inició la secuencia de corte; separación pendiente.",
            "confirmado": "Firmware reportó corte confirmado por descenso; no es verificación visual.",
            "sin_confirmar": "Secuencia de corte terminada SIN CONFIRMAR separación."}[outcome]
    return status, text, dict(packet)
