"""
Servidor MCP: conecta Garmin Connect y Strava como herramientas
que Claude puede usar en tiempo real.

Para correrlo localmente (pruebas):
    python server.py

En produccion (Railway) se levanta con uvicorn, ver Procfile.
"""
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.transport_security import TransportSecuritySettings

import garmin_client
import strava_client
from auth_provider import provider as oauth_provider, login_routes

SERVER_URL = os.environ["SERVER_URL"].rstrip("/")
SERVER_HOST = urlparse(SERVER_URL).netloc  # ej: web-production-63e12.up.railway.app

mcp = FastMCP(
    "garmin-strava-coach",
    auth_server_provider=oauth_provider,
    auth=AuthSettings(
        issuer_url=SERVER_URL,
        resource_server_url=f"{SERVER_URL}/mcp",
        client_registration_options=ClientRegistrationOptions(
            enabled=True,
            valid_scopes=["mcp"],
            default_scopes=["mcp"],
        ),
        revocation_options=RevocationOptions(enabled=True),
    ),
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[SERVER_HOST, "localhost", "localhost:8000", "127.0.0.1:8000"],
        allowed_origins=[SERVER_URL, "http://localhost:8000", "http://127.0.0.1:8000"],
    ),
)


# ---------- Herramientas de Garmin ----------

@mcp.tool()
def garmin_get_sleep(days: int = 7) -> list:
    """Obtiene datos de sueño de Garmin de los ultimos N dias: horas de sueño,
    fases (profundo/liviano/REM), sleep score, HRV promedio nocturno y
    frecuencia cardiaca en reposo. Usar para evaluar recuperacion."""
    return garmin_client.get_sleep(days)


@mcp.tool()
def garmin_get_hrv(days: int = 7) -> list:
    """Obtiene datos de variabilidad de frecuencia cardiaca (HRV) de Garmin
    de los ultimos N dias, incluyendo el promedio, el estado (balanced/low/etc)
    y el rango base personal. Util para medir estres y recuperacion del sistema nervioso."""
    return garmin_client.get_hrv(days)


@mcp.tool()
def garmin_get_body_battery(days: int = 7) -> list:
    """Obtiene niveles de Body Battery de Garmin de los ultimos N dias
    (energia acumulada/gastada). Util para ver si el cuerpo esta recuperado
    para entrenar fuerte hoy."""
    return garmin_client.get_body_battery(days)


@mcp.tool()
def garmin_get_training_readiness() -> dict:
    """Obtiene el puntaje de 'preparacion para entrenar' de hoy segun Garmin,
    que combina sueño, HRV, carga de entrenamiento reciente y tiempo de
    recuperacion. Es el indicador mas directo de si conviene entrenar fuerte,
    moderado, o descansar hoy."""
    return garmin_client.get_training_readiness()


@mcp.tool()
def garmin_get_training_status() -> dict:
    """Obtiene el estado de carga de entrenamiento segun Garmin (productive,
    maintaining, overreaching, detraining, etc), util para saber si el
    volumen/intensidad actual es sostenible o hay riesgo de sobreentrenamiento."""
    return garmin_client.get_training_status()


@mcp.tool()
def garmin_get_activities(limit: int = 10) -> list:
    """Obtiene las ultimas N actividades registradas en Garmin, con duracion,
    distancia, frecuencia cardiaca y training effect aerobico/anaerobico."""
    return garmin_client.get_activities(limit)


@mcp.tool()
def garmin_get_max_metrics() -> dict:
    """Obtiene el VO2max de running y de ciclismo del dia de hoy segun Garmin,
    mas el fitness age. Son las metricas de fitness aerobico mas importantes
    para proyectar rendimiento en carrera y en bici."""
    return garmin_client.get_max_metrics()


@mcp.tool()
def garmin_get_race_predictions() -> dict:
    """Obtiene las predicciones de tiempo de Garmin para 5K, 10K, media maraton
    y maraton basadas en el VO2max y actividades recientes. Util para evaluar
    si el objetivo de marca personal en la media maraton es realista."""
    return garmin_client.get_race_predictions()


@mcp.tool()
def garmin_get_lactate_threshold() -> dict:
    """Obtiene el umbral de lactato de running: frecuencia cardiaca y ritmo
    en el umbral. Referencia clave para definir zonas de entrenamiento
    y planificar intensidades de sesiones de calidad."""
    return garmin_client.get_lactate_threshold()


@mcp.tool()
def garmin_get_cycling_ftp() -> dict:
    """Obtiene el FTP (Functional Threshold Power) de ciclismo en watts segun Garmin.
    Es la potencia maxima sostenible durante 1 hora y la referencia principal
    para definir zonas de entrenamiento en bici para el triatlon."""
    return garmin_client.get_cycling_ftp()


@mcp.tool()
def garmin_get_endurance_score(days: int = 28) -> dict:
    """Obtiene el Endurance Score de Garmin de los ultimos N dias: resistencia
    aerobica acumulada. Util para proyectar rendimiento en media maraton y
    triatlon, y para ver si la base aerobica esta creciendo o cayendo."""
    return garmin_client.get_endurance_score(days)


@mcp.tool()
def garmin_get_running_tolerance(days: int = 28) -> list:
    """Obtiene la tolerancia al running de las ultimas semanas: que tan bien
    esta absorbiendo el cuerpo la carga de carrera. Especialmente util post-lesion
    para detectar riesgo de recaida por exceso de carga antes de que ocurra."""
    return garmin_client.get_running_tolerance(days)


@mcp.tool()
def garmin_get_personal_records() -> dict:
    """Obtiene los records personales registrados en Garmin (5K, 10K,
    media maraton, maraton, etc). Necesario para que el coach sepa la
    marca actual real y pueda evaluar si el objetivo de agosto es realista."""
    return garmin_client.get_personal_records()


@mcp.tool()
def garmin_get_respiration_data() -> dict:
    """Obtiene la frecuencia respiratoria durante el sueño de anoche.
    Complementa el HRV para detectar estados de enfermedad o
    sobreentrenamiento antes de que se noten en el rendimiento."""
    return garmin_client.get_respiration_data()


@mcp.tool()
def garmin_get_spo2_data() -> dict:
    """Obtiene la saturacion de oxigeno (SpO2) nocturna de anoche.
    Util para detectar recuperacion incompleta, especialmente en
    periodos de carga alta de entrenamiento."""
    return garmin_client.get_spo2_data()


@mcp.tool()
def garmin_get_hill_score(days: int = 28) -> dict:
    """Obtiene el Hill Score de Garmin de los ultimos N dias: capacidad
    en subidas y potencia. Relevante para el bloque de ciclismo del triatlon."""
    return garmin_client.get_hill_score(days)


import workout_builder

# ---------- Herramientas de Workouts ----------

@mcp.tool()
def garmin_schedule_easy_run(
    name: str,
    date: str,
    total_minutes: int,
    description: str = ""
) -> dict:
    """Crea un rodaje suave (Z2) y lo agenda en el calendario de Garmin.
    Parametros: name (nombre del workout), date (YYYY-MM-DD), total_minutes
    (duracion total incluyendo entrada y vuelta en calor), description (opcional).
    Ejemplo: rodaje regenerativo de 45 minutos."""
    w = workout_builder.build_easy_run(name, total_minutes, description)
    return workout_builder.upload_and_schedule_workout(w, date)


@mcp.tool()
def garmin_schedule_tempo_run(
    name: str,
    date: str,
    warmup_minutes: int,
    tempo_minutes: int,
    cooldown_minutes: int,
    description: str = ""
) -> dict:
    """Crea un tempo run (Z4 continuo) y lo agenda en Garmin.
    Parametros: name, date (YYYY-MM-DD), warmup_minutes, tempo_minutes
    (parte a ritmo de umbral), cooldown_minutes, description (opcional).
    Ejemplo: 10 min entrada + 20 min tempo + 10 min vuelta calma."""
    w = workout_builder.build_tempo_run(name, warmup_minutes, tempo_minutes, cooldown_minutes, description)
    return workout_builder.upload_and_schedule_workout(w, date)


@mcp.tool()
def garmin_schedule_interval_run(
    name: str,
    date: str,
    warmup_minutes: int,
    interval_distance_meters: int,
    repetitions: int,
    recovery_seconds: int,
    cooldown_minutes: int,
    interval_hr_zone: int = 5,
    description: str = ""
) -> dict:
    """Crea una sesion de intervalos por distancia y la agenda en Garmin.
    Parametros: name, date (YYYY-MM-DD), warmup_minutes, interval_distance_meters
    (ej: 1000 para 1km), repetitions (ej: 4), recovery_seconds (entre repeticiones),
    cooldown_minutes, interval_hr_zone (4=umbral, 5=VO2max), description (opcional).
    Ejemplo: 4x1000m en Z5 con 90 seg de recuperacion."""
    w = workout_builder.build_interval_run(
        name, warmup_minutes, interval_distance_meters,
        repetitions, recovery_seconds, cooldown_minutes,
        interval_hr_zone, description
    )
    return workout_builder.upload_and_schedule_workout(w, date)


@mcp.tool()
def garmin_schedule_long_run(
    name: str,
    date: str,
    total_minutes: int,
    description: str = ""
) -> dict:
    """Crea una tirada larga (Z2 con bloque final en Z3) y la agenda en Garmin.
    Parametros: name, date (YYYY-MM-DD), total_minutes, description (opcional).
    Ejemplo: tirada larga de 100 minutos del domingo."""
    w = workout_builder.build_long_run(name, total_minutes, description)
    return workout_builder.upload_and_schedule_workout(w, date)


@mcp.tool()
def garmin_schedule_easy_bike(
    name: str,
    date: str,
    total_minutes: int,
    description: str = ""
) -> dict:
    """Crea un rodaje suave de ciclismo (Z2) y lo agenda en Garmin.
    Para el bloque de triatlon. Parametros: name, date (YYYY-MM-DD),
    total_minutes, description (opcional)."""
    w = workout_builder.build_easy_bike(name, total_minutes, description)
    return workout_builder.upload_and_schedule_workout(w, date)


@mcp.tool()
def garmin_get_scheduled_workouts(date: str = "") -> list:
    """Devuelve los workouts ya agendados en Garmin para el mes de la fecha indicada
    (YYYY-MM-DD). Si no se pasa fecha, usa el mes actual. Usar antes de agendar
    para no duplicar sesiones."""
    return workout_builder.get_scheduled_workouts_for_week(date or None)


@mcp.tool()
def garmin_delete_scheduled_workout(scheduled_workout_id: str) -> dict:
    """Borra un workout del calendario de Garmin por su scheduled_id (no borra
    el workout en si, solo lo quita del calendario). Usar para reemplazar una
    sesion que cambio de plan."""
    return workout_builder.delete_scheduled_workout(scheduled_workout_id)


# ---------- Herramientas de Strava ----------

@mcp.tool()
def strava_get_activities(limit: int = 10) -> list:
    """Obtiene las ultimas N actividades de Strava, con tipo, distancia,
    tiempo, ritmo/velocidad, desnivel, FC y suffer score (carga percibida)."""
    return strava_client.get_activities(limit)


@mcp.tool()
def strava_get_activity_detail(activity_id: int) -> dict:
    """Obtiene el detalle completo de una actividad puntual de Strava por su ID,
    incluyendo splits, segmentos y metricas avanzadas si estan disponibles."""
    return strava_client.get_activity_detail(activity_id)


@mcp.tool()
def strava_get_athlete_stats() -> dict:
    """Obtiene estadisticas acumuladas del atleta en Strava: totales de
    distancia/tiempo de la semana, mes reciente y todo el historial,
    separado por tipo de actividad."""
    return strava_client.get_athlete_stats()


# App ASGI: la app MCP (con OAuth ya integrado por el SDK) + nuestras
# rutas propias de login (la pantalla HTML de usuario/contraseña).
app = mcp.streamable_http_app()
for route in login_routes:
    app.router.routes.append(route)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
