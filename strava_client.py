"""
Cliente de la API oficial de Strava (REST + OAuth2).

Mejoras sobre la version original:
- Cache en memoria con TTL diferenciado (igual patron que garmin_client.py)
- Retry automatico (1 reintento) en errores de red transitorio
- Refresh token persistente en variable de entorno (Strava no lo rota,
  pero si alguna vez cambia se detectara con un error claro)

TTLs:
- 5 min: actividades recientes (por si acaba de sincronizar una)
- 60 min: stats acumulados del atleta (cambian poco)
- Sin cache: detalle de actividad puntual (se pide por ID especifico, siempre fresco)
"""
import os
import time
import logging
import httpx

logger = logging.getLogger(__name__)

# ---------- Token OAuth ----------

_token_cache: dict = {"access_token": None, "expires_at": 0}

TTL_ACTIVITIES = 300    # 5 min
TTL_STATS      = 3600   # 60 min

# ---------- Cache (mismo patron que garmin_client) ----------

_cache: dict = {}


def _cached(key: str, ttl: int, fn):
    """Ejecuta fn() y cachea el resultado por ttl segundos."""
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


# ---------- Autenticacion ----------

def _get_access_token() -> str:
    """Devuelve un access token valido, refrescandolo si expiró."""
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["access_token"]

    logger.info("Refrescando access token de Strava")
    resp = httpx.post(
        "https://www.strava.com/oauth/token",
        data={
            "client_id": os.environ["STRAVA_CLIENT_ID"],
            "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
            "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = data["expires_at"]

    # Si Strava alguna vez rotara el refresh token, lo detectamos acá
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != os.environ.get("STRAVA_REFRESH_TOKEN"):
        logger.warning(
            "Strava devolvio un refresh_token nuevo. "
            "Actualizá la variable STRAVA_REFRESH_TOKEN en Railway: %s", new_refresh
        )

    return data["access_token"]


# ---------- HTTP con retry ----------

def _get(path: str, params: dict = None, retries: int = 1):
    """GET a la API de Strava con 1 reintento ante errores transitorios de red."""
    for attempt in range(retries + 1):
        try:
            token = _get_access_token()
            resp = httpx.get(
                f"https://www.strava.com/api/v3{path}",
                headers={"Authorization": f"Bearer {token}"},
                params=params or {},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.TimeoutException as e:
            if attempt < retries:
                logger.warning("Timeout en Strava %s, reintentando... (%d/%d)", path, attempt + 1, retries)
                time.sleep(1)
            else:
                raise
        except httpx.HTTPStatusError as e:
            # No reintentamos errores HTTP (4xx/5xx) salvo 429 y 5xx transitorios
            if attempt < retries and e.response.status_code in (429, 500, 502, 503, 504):
                wait = int(e.response.headers.get("Retry-After", 2))
                logger.warning("Strava %s devolvio %d, reintentando en %ds", path, e.response.status_code, wait)
                time.sleep(wait)
            else:
                raise
        except httpx.NetworkError as e:
            if attempt < retries:
                logger.warning("Error de red en Strava %s, reintentando... (%d/%d)", path, attempt + 1, retries)
                time.sleep(1)
            else:
                raise


# ---------- Funciones de datos ----------

def get_activities(limit: int = 10):
    """Ultimas N actividades de Strava."""
    def fetch():
        try:
            data = _get("/athlete/activities", {"per_page": limit})
            return [
                {
                    "id": a.get("id"),
                    "name": a.get("name"),
                    "type": a.get("type"),
                    "start_date": a.get("start_date_local"),
                    "distance_meters": a.get("distance"),
                    "moving_time_seconds": a.get("moving_time"),
                    "elapsed_time_seconds": a.get("elapsed_time"),
                    "total_elevation_gain": a.get("total_elevation_gain"),
                    "avg_speed_mps": a.get("average_speed"),
                    "max_speed_mps": a.get("max_speed"),
                    "avg_hr": a.get("average_heartrate"),
                    "max_hr": a.get("max_heartrate"),
                    "avg_watts": a.get("average_watts"),
                    "suffer_score": a.get("suffer_score"),
                }
                for a in data
            ]
        except httpx.HTTPStatusError as e:
            return {"error": f"Strava API error {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"error": str(e)}
    return _cached(f"activities_{limit}", TTL_ACTIVITIES, fetch)


def get_activity_detail(activity_id: int):
    """Detalle completo de una actividad puntual. Sin cache — se pide por ID especifico."""
    try:
        return _get(f"/activities/{activity_id}")
    except httpx.HTTPStatusError as e:
        return {"error": f"Strava API error {e.response.status_code}: {e.response.text}"}
    except Exception as e:
        return {"error": str(e)}


def get_athlete_stats():
    """Estadisticas acumuladas del atleta (totales del año, del mes, records)."""
    def fetch():
        try:
            athlete = _get("/athlete")
            athlete_id = athlete["id"]
            return _get(f"/athletes/{athlete_id}/stats")
        except httpx.HTTPStatusError as e:
            return {"error": f"Strava API error {e.response.status_code}: {e.response.text}"}
        except Exception as e:
            return {"error": str(e)}
    return _cached("athlete_stats", TTL_STATS, fetch)
