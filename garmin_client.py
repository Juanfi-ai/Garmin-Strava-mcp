"""
Cliente de Garmin Connect.
Usa la libreria no oficial `garminconnect`, que se autentica con
usuario/contraseña reales de Garmin Connect (no hay API publica oficial
para cuentas de consumidor).

Cache en memoria con TTL diferenciado por tipo de dato para evitar
rate limiting (429) cuando Claude llama multiples herramientas seguidas:
- 10 min: datos del dia (sueño, HRV, body battery, readiness, SpO2, respiracion)
- 60 min: datos estables (VO2max, FTP, race predictions, records, endurance)
-  5 min: actividades recientes (por si acaba de sincronizar)
"""
import os
import time
import logging
import datetime
from garminconnect import Garmin

logger = logging.getLogger(__name__)

_client = None

# Cache: { cache_key: (timestamp, data) }
_cache: dict = {}

TTL_DAY_METRICS   = 600    # 10 min — sueño, HRV, body battery, readiness, SpO2, respiracion
TTL_STABLE        = 3600   # 60 min — VO2max, FTP, race predictions, records, endurance
TTL_ACTIVITIES    = 300    #  5 min — actividades recientes


# ---------- Sesion ----------

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
    logger.info("Sesion de Garmin iniciada")
    return client


def _date_str(d: datetime.date) -> str:
    return d.strftime("%Y-%m-%d")


# ---------- Cache ----------

def _cache_get(key: str):
    """Devuelve el valor cacheado si existe y no expiró, o None."""
    entry = _cache.get(key)
    if entry is None:
        return None
    ts, data = entry
    # El TTL ya fue validado al guardar — chequeamos si sigue vigente
    return data  # el chequeo de expiración está en _cached()


def _cached(key: str, ttl: int, fn):
    """Ejecuta fn() y cachea el resultado por ttl segundos.
    Si el resultado ya está en cache y no expiró, devuelve el cacheado."""
    now = time.time()
    entry = _cache.get(key)
    if entry is not None:
        ts, data = entry
        if now - ts < ttl:
            logger.debug("Cache hit: %s", key)
            return data
    logger.debug("Cache miss: %s", key)
    result = fn()
    _cache[key] = (now, result)
    return result


# ---------- Funciones de datos ----------

def get_sleep(days: int = 7):
    """Datos de sueño de los ultimos N dias."""
    def fetch():
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
    return _cached(f"sleep_{days}", TTL_DAY_METRICS, fetch)


def get_hrv(days: int = 7):
    """Datos de HRV de los ultimos N dias."""
    def fetch():
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
    return _cached(f"hrv_{days}", TTL_DAY_METRICS, fetch)


def get_body_battery(days: int = 7):
    """Niveles de Body Battery de los ultimos N dias."""
    def fetch():
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
    return _cached(f"body_battery_{days}", TTL_DAY_METRICS, fetch)


def get_training_readiness():
    """Puntaje de preparacion para entrenar hoy."""
    def fetch():
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
    return _cached("training_readiness", TTL_DAY_METRICS, fetch)


def get_training_status():
    """Estado de carga de entrenamiento."""
    def fetch():
        client = get_client()
        today = _date_str(datetime.date.today())
        try:
            return client.get_training_status(today)
        except Exception as e:
            return {"error": str(e)}
    return _cached("training_status", TTL_DAY_METRICS, fetch)


def get_max_metrics():
    """VO2max de running y ciclismo, fitness age."""
    def fetch():
        client = get_client()
        today = _date_str(datetime.date.today())
        try:
            data = client.get_max_metrics(today)
            if not data:
                return {}
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
    return _cached("max_metrics", TTL_STABLE, fetch)


def get_race_predictions():
    """Predicciones de tiempo para 5K, 10K, media y maraton."""
    def fetch():
        client = get_client()
        try:
            data = client.get_race_predictions()
            if not data:
                return {}
            return {
                "time_5k_seconds": data.get("time5K") or data.get("racePrediction5k"),
                "time_10k_seconds": data.get("time10K") or data.get("racePrediction10k"),
                "time_half_marathon_seconds": data.get("timeHalfMarathon") or data.get("racePredictionHalfMarathon"),
                "time_marathon_seconds": data.get("timeMarathon") or data.get("racePredictionMarathon"),
                "raw": data,
            }
        except Exception as e:
            return {"error": str(e)}
    return _cached("race_predictions", TTL_STABLE, fetch)


def get_lactate_threshold():
    """Umbral de lactato: ritmo y FC."""
    def fetch():
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
    return _cached("lactate_threshold", TTL_STABLE, fetch)


def get_cycling_ftp():
    """FTP de ciclismo en watts."""
    def fetch():
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
    return _cached("cycling_ftp", TTL_STABLE, fetch)


def get_endurance_score(days: int = 28):
    """Endurance Score de los ultimos N dias."""
    def fetch():
        client = get_client()
        today = datetime.date.today()
        start = today - datetime.timedelta(days=days - 1)
        try:
            return client.get_endurance_score(_date_str(start), _date_str(today))
        except Exception as e:
            return {"error": str(e)}
    return _cached(f"endurance_score_{days}", TTL_STABLE, fetch)


def get_running_tolerance(days: int = 28):
    """Tolerancia al running de las ultimas semanas."""
    def fetch():
        client = get_client()
        today = datetime.date.today()
        start = today - datetime.timedelta(days=days - 1)
        try:
            return client.get_running_tolerance(_date_str(start), _date_str(today), aggregation="weekly")
        except Exception as e:
            return {"error": str(e)}
    return _cached(f"running_tolerance_{days}", TTL_STABLE, fetch)


def get_personal_records():
    """Records personales registrados en Garmin."""
    def fetch():
        client = get_client()
        try:
            return client.get_personal_record()
        except Exception as e:
            return {"error": str(e)}
    return _cached("personal_records", TTL_STABLE, fetch)


def get_respiration_data():
    """Frecuencia respiratoria durante el sueño de anoche."""
    def fetch():
        client = get_client()
        today = _date_str(datetime.date.today())
        try:
            return client.get_respiration_data(today)
        except Exception as e:
            return {"error": str(e)}
    return _cached("respiration", TTL_DAY_METRICS, fetch)


def get_spo2_data():
    """Saturacion de oxigeno nocturna de anoche."""
    def fetch():
        client = get_client()
        today = _date_str(datetime.date.today())
        try:
            return client.get_spo2_data(today)
        except Exception as e:
            return {"error": str(e)}
    return _cached("spo2", TTL_DAY_METRICS, fetch)


def get_hill_score(days: int = 28):
    """Hill Score de los ultimos N dias."""
    def fetch():
        client = get_client()
        today = datetime.date.today()
        start = today - datetime.timedelta(days=days - 1)
        try:
            return client.get_hill_score(_date_str(start), _date_str(today))
        except Exception as e:
            return {"error": str(e)}
    return _cached(f"hill_score_{days}", TTL_STABLE, fetch)


def get_activities(limit: int = 10):
    """Ultimas N actividades de Garmin."""
    def fetch():
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
    return _cached(f"activities_{limit}", TTL_ACTIVITIES, fetch)
