"""
Cliente de Garmin Connect.
Usa la libreria no oficial `garminconnect`, que se autentica con
usuario/contraseña reales de Garmin Connect (no hay API publica oficial
para cuentas de consumidor).
"""
import os
import datetime
from garminconnect import Garmin

_client = None


def get_client():
    """Devuelve un cliente autenticado, reutilizando sesion si ya existe."""
    global _client
    if _client is not None:
        return _client

    email = os.environ["GARMIN_EMAIL"]
    password = os.environ["GARMIN_PASSWORD"]

    client = Garmin(email, password)
    client.login()
    _client = client
    return client


def _date_str(d: datetime.date) -> str:
    return d.strftime("%Y-%m-%d")


def get_sleep(days: int = 7):
    """Datos de sueño de los ultimos `days` dias."""
    client = get_client()
    today = datetime.date.today()
    results = []
    for i in range(days):
        day = today - datetime.timedelta(days=i)
        try:
            data = client.get_sleep_data(_date_str(day))
            if data and data.get("dailySleepDTO"):
                dto = data["dailySleepDTO"]
                results.append({
                    "date": _date_str(day),
                    "sleep_time_seconds": dto.get("sleepTimeSeconds"),
                    "deep_sleep_seconds": dto.get("deepSleepSeconds"),
                    "light_sleep_seconds": dto.get("lightSleepSeconds"),
                    "rem_sleep_seconds": dto.get("remSleepSeconds"),
                    "awake_seconds": dto.get("awakeSleepSeconds"),
                    "sleep_score": (data.get("sleepScores") or {}).get("overall", {}).get("value"),
                    "avg_overnight_hrv": data.get("avgOvernightHrv"),
                    "resting_heart_rate": data.get("restingHeartRate"),
                })
        except Exception:
            continue
    return results


def get_hrv(days: int = 7):
    """Datos de HRV (variabilidad de frecuencia cardiaca) de los ultimos `days` dias."""
    client = get_client()
    today = datetime.date.today()
    results = []
    for i in range(days):
        day = today - datetime.timedelta(days=i)
        try:
            data = client.get_hrv_data(_date_str(day))
            if data and data.get("hrvSummary"):
                summary = data["hrvSummary"]
                results.append({
                    "date": _date_str(day),
                    "last_night_avg": summary.get("lastNightAvg"),
                    "last_night_5min_high": summary.get("lastNight5MinHigh"),
                    "status": summary.get("status"),
                    "weekly_avg": summary.get("weeklyAvg"),
                    "baseline_low": (summary.get("baseline") or {}).get("balancedLow"),
                    "baseline_high": (summary.get("baseline") or {}).get("balancedUpper"),
                })
        except Exception:
            continue
    return results


def get_body_battery(days: int = 7):
    """Niveles de Body Battery de los ultimos `days` dias."""
    client = get_client()
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days - 1)
    try:
        data = client.get_body_battery(_date_str(start), _date_str(today))
        results = []
        for entry in data or []:
            results.append({
                "date": entry.get("date"),
                "charged": entry.get("charged"),
                "drained": entry.get("drained"),
                "highest": entry.get("highestLevel") if "highestLevel" in entry else None,
                "lowest": entry.get("lowestLevel") if "lowestLevel" in entry else None,
            })
        return results
    except Exception as e:
        return {"error": str(e)}


def get_training_readiness():
    """Puntaje de 'preparacion para entrenar' de hoy (combina sueño, HRV, carga, etc)."""
    client = get_client()
    today = _date_str(datetime.date.today())
    try:
        data = client.get_training_readiness(today)
        if not data:
            return {}
        entry = data[0] if isinstance(data, list) else data
        return {
            "score": entry.get("score"),
            "level": entry.get("level"),
            "feedback": entry.get("feedbackLong") or entry.get("feedbackShort"),
            "sleep_score_factor": entry.get("sleepScoreFactorPercent"),
            "hrv_factor": entry.get("hrvFactorPercent"),
            "recovery_time_factor": entry.get("recoveryTimeFactorPercent"),
            "training_load_factor": entry.get("acuteLoadFactorPercent"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_training_status():
    """Estado de carga de entrenamiento (productive, overreaching, detraining, etc)."""
    client = get_client()
    today = _date_str(datetime.date.today())
    try:
        data = client.get_training_status(today)
        return data
    except Exception as e:
        return {"error": str(e)}


def get_activities(limit: int = 10):
    """Ultimas `limit` actividades registradas en Garmin (puede incluir las sincronizadas desde otros dispositivos)."""
    client = get_client()
    try:
        activities = client.get_activities(0, limit)
        results = []
        for a in activities:
            results.append({
                "activity_id": a.get("activityId"),
                "name": a.get("activityName"),
                "type": (a.get("activityType") or {}).get("typeKey"),
                "start_time": a.get("startTimeLocal"),
                "duration_seconds": a.get("duration"),
                "distance_meters": a.get("distance"),
                "avg_hr": a.get("averageHR"),
                "max_hr": a.get("maxHR"),
                "calories": a.get("calories"),
                "training_effect_aerobic": a.get("aerobicTrainingEffect"),
                "training_effect_anaerobic": a.get("anaerobicTrainingEffect"),
            })
        return results
    except Exception as e:
        return {"error": str(e)}
