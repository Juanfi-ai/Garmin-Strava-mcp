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
