"""
Cliente de la API oficial de Strava (REST + OAuth2).
Usa un refresh_token de larga duracion para obtener access_tokens nuevos
cada vez que hace falta (los access_token de Strava duran 6 horas).
"""
import os
import time
import httpx

_token_cache = {"access_token": None, "expires_at": 0}


def _get_access_token() -> str:
    now = time.time()
    if _token_cache["access_token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["access_token"]

    resp = httpx.post("https://www.strava.com/oauth/token", data={
        "client_id": os.environ["STRAVA_CLIENT_ID"],
        "client_secret": os.environ["STRAVA_CLIENT_SECRET"],
        "refresh_token": os.environ["STRAVA_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    })
    resp.raise_for_status()
    data = resp.json()
    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = data["expires_at"]
    return data["access_token"]


def _get(path: str, params: dict = None):
    token = _get_access_token()
    resp = httpx.get(
        f"https://www.strava.com/api/v3{path}",
        headers={"Authorization": f"Bearer {token}"},
        params=params or {},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def get_activities(limit: int = 10):
    """Ultimas `limit` actividades de Strava."""
    try:
        data = _get("/athlete/activities", {"per_page": limit})
        results = []
        for a in data:
            results.append({
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
            })
        return results
    except httpx.HTTPStatusError as e:
        return {"error": f"Strava API error {e.response.status_code}: {e.response.text}"}


def get_activity_detail(activity_id: int):
    """Detalle completo de una actividad puntual de Strava."""
    try:
        return _get(f"/activities/{activity_id}")
    except httpx.HTTPStatusError as e:
        return {"error": f"Strava API error {e.response.status_code}: {e.response.text}"}


def get_athlete_stats():
    """Estadisticas acumuladas del atleta (totales del año, del mes, records, etc)."""
    try:
        athlete = _get("/athlete")
        athlete_id = athlete["id"]
        return _get(f"/athletes/{athlete_id}/stats")
    except httpx.HTTPStatusError as e:
        return {"error": f"Strava API error {e.response.status_code}: {e.response.text}"}
