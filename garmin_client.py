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


def get_max_metrics():
    """VO2max de running y ciclismo del dia de hoy segun Garmin.
    Incluye VO2max actual, historico reciente y fitness age."""
    client = get_client()
    today = _date_str(datetime.date.today())
    try:
        data = client.get_max_metrics(today)
        if not data:
            return {}
        # get_max_metrics devuelve una lista de entradas, tomamos la mas reciente
        entry = data[0] if isinstance(data, list) else data
        return {
            "calendar_date": entry.get("calendarDate"),
            "vo2max_running": entry.get("vo2MaxPreciseValue") or entry.get("vo2MaxValue"),
            "vo2max_cycling": entry.get("vo2MaxCyclingValue"),
            "fitness_age": entry.get("fitnessAge"),
            "fitness_age_description": entry.get("fitnessAgeDescription"),
        }
    except Exception as e:
        return {"error": str(e)}


def get_race_predictions():
    """Predicciones de tiempo de carrera para 5K, 10K, media maraton y maraton
    segun el algoritmo de Garmin, basado en VO2max y actividades recientes."""
    client = get_client()
    try:
        data = client.get_race_predictions()
        if not data:
            return {}
        # Normalizar las claves que devuelve Garmin (pueden variar por firmware)
        return {
            "time_5k_seconds": data.get("time5K") or data.get("racePrediction5k"),
            "time_10k_seconds": data.get("time10K") or data.get("racePrediction10k"),
            "time_half_marathon_seconds": data.get("timeHalfMarathon") or data.get("racePredictionHalfMarathon"),
            "time_marathon_seconds": data.get("timeMarathon") or data.get("racePredictionMarathon"),
            "raw": data,  # incluimos el raw por si las claves cambian
        }
    except Exception as e:
        return {"error": str(e)}


def get_lactate_threshold():
    """Umbral de lactato: ritmo y frecuencia cardiaca en el umbral,
    util para definir zonas de entrenamiento de running."""
    client = get_client()
    try:
        data = client.get_lactate_threshold(latest=True)
        if not data:
            return {}
        entry = data[0] if isinstance(data, list) else data
        return {
            "date": entry.get("calendarDate"),
            "heart_rate_bpm": entry.get("heartRate") or (entry.get("lactateThresholdHeartRate") or {}).get("value"),
            "pace_seconds_per_km": entry.get("pace") or (entry.get("lactateThresholdPace") or {}).get("value"),
            "raw": entry,
        }
    except Exception as e:
        return {"error": str(e)}


def get_cycling_ftp():
    """FTP (Functional Threshold Power) de ciclismo en watts segun Garmin.
    Es la potencia maxima sostenible durante 1 hora, referencia clave
    para zonas de entrenamiento en bici."""
    client = get_client()
    try:
        data = client.get_cycling_ftp()
        if not data:
            return {}
        entry = data[0] if isinstance(data, list) else data
        return {
            "ftp_watts": entry.get("functionalThresholdPower") or entry.get("value"),
            "date": entry.get("calendarDate") or entry.get("date"),
            "raw": entry,
        }
    except Exception as e:
        return {"error": str(e)}


def get_endurance_score(days: int = 28):
    """Endurance Score de Garmin de los ultimos N dias: resistencia aerobica
    acumulada, util para proyectar rendimiento en media maraton y triatlon."""
    client = get_client()
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days - 1)
    try:
        data = client.get_endurance_score(_date_str(start), _date_str(today))
        return data
    except Exception as e:
        return {"error": str(e)}


def get_running_tolerance(days: int = 28):
    """Tolerancia al running de las ultimas semanas: que tan bien esta
    absorbiendo el cuerpo la carga de carrera. Util para detectar riesgo
    de lesion por exceso de carga, especialmente relevante post-lesion."""
    client = get_client()
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days - 1)
    try:
        data = client.get_running_tolerance(_date_str(start), _date_str(today), aggregation="weekly")
        return data
    except Exception as e:
        return {"error": str(e)}


def get_personal_records():
    """Records personales registrados en Garmin (5K, 10K, media maraton, etc.).
    Necesario para evaluar si el objetivo de marca personal es realista."""
    client = get_client()
    try:
        return client.get_personal_record()
    except Exception as e:
        return {"error": str(e)}


def get_respiration_data():
    """Frecuencia respiratoria durante el sueño de anoche. Complementa el HRV
    para detectar estados de enfermedad o sobreentrenamiento."""
    client = get_client()
    today = _date_str(datetime.date.today())
    try:
        return client.get_respiration_data(today)
    except Exception as e:
        return {"error": str(e)}


def get_spo2_data():
    """Saturacion de oxigeno (SpO2) nocturna de anoche. Util para detectar
    recuperacion incompleta, especialmente en periodos de carga alta."""
    client = get_client()
    today = _date_str(datetime.date.today())
    try:
        return client.get_spo2_data(today)
    except Exception as e:
        return {"error": str(e)}


def get_hill_score(days: int = 28):
    """Hill Score de Garmin de los ultimos N dias: capacidad en subidas
    y potencia. Util para el bloque de ciclismo del triatlon."""
    client = get_client()
    today = datetime.date.today()
    start = today - datetime.timedelta(days=days - 1)
    try:
        return client.get_hill_score(_date_str(start), _date_str(today))
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
