"""
Servidor MCP: conecta Garmin Connect y Strava como herramientas
que Claude puede usar en tiempo real.

Para correrlo localmente (pruebas):
    python server.py

En produccion (Railway) se levanta con uvicorn, ver Procfile.
"""
import os
from dotenv import load_dotenv

load_dotenv()

from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.requests import Request

import garmin_client
import strava_client

mcp = FastMCP("garmin-strava-coach")


class BearerAuthMiddleware(BaseHTTPMiddleware):
    """Exige un Bearer token fijo (MCP_AUTH_TOKEN) en cada request.
    Protege el servidor de que cualquiera con la URL pueda leer tus datos."""

    async def dispatch(self, request: Request, call_next):
        expected = os.environ.get("MCP_AUTH_TOKEN")
        if expected:
            auth_header = request.headers.get("authorization", "")
            token = auth_header.removeprefix("Bearer ").strip()
            if token != expected:
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        return await call_next(request)


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


# App ASGI con el middleware de autenticacion ya aplicado.
# Esto es lo que uvicorn levanta en produccion (ver Procfile / comando de start).
app = mcp.streamable_http_app()
app.add_middleware(BearerAuthMiddleware)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
