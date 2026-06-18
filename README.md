# Garmin + Strava MCP Server

Servidor MCP que le da a Claude acceso en tiempo real a tus datos de Garmin Connect y Strava, con capacidad de crear y agendar workouts directamente en tu calendario de Garmin. Diseñado para funcionar como coach de entrenamiento personalizado dentro de Claude.ai.

## Qué hace

- Lee en tiempo real: sueño, HRV, body battery, SpO2, respiración, training readiness, training status, endurance score, running tolerance, VO2max, fitness age, FTP de ciclismo, lactate threshold, race predictions, records personales, actividades de Garmin y Strava.
- Crea y agenda workouts estructurados (rodajes suaves, tempo, intervalos, tiradas largas, bici) directamente en tu calendario de Garmin. Aparecen en tu reloj como workouts guiados con zonas de FC.
- Autenticación OAuth 2.1 completa con pantalla de login propia, compatible con el sistema de conectores custom de Claude.ai.

## Archivos del proyecto

| Archivo | Qué hace |
|---|---|
| `server.py` | Servidor MCP principal. Expone las 26 herramientas y maneja el OAuth. |
| `auth_provider.py` | Servidor de autorización OAuth 2.1 con pantalla de login HTML. |
| `garmin_client.py` | Cliente de Garmin Connect (librería no oficial). |
| `strava_client.py` | Cliente de la API oficial de Strava (OAuth2). |
| `workout_builder.py` | Constructor de workouts estructurados para Garmin. |
| `requirements.txt` | Dependencias exactas. |
| `.env.example` | Plantilla de variables de entorno. |
| `.python-version` | Fija Python 3.13 para Railway. |
| `Procfile` | Comando de inicio para Railway. |

## Herramientas disponibles (26)

### Recuperación y estado diario
- `garmin_get_sleep` — sueño: horas, fases, sleep score, HRV nocturno, FC reposo
- `garmin_get_hrv` — HRV diario, estado, rango base personal
- `garmin_get_body_battery` — energía acumulada/gastada
- `garmin_get_respiration_data` — frecuencia respiratoria nocturna
- `garmin_get_spo2_data` — saturación de oxígeno nocturna
- `garmin_get_training_readiness` — puntaje de preparación para entrenar hoy

### Carga y progresión
- `garmin_get_training_status` — estado de carga (productive / maintaining / overreaching / detraining)
- `garmin_get_endurance_score` — resistencia aeróbica acumulada
- `garmin_get_running_tolerance` — absorción de carga de carrera semana a semana
- `garmin_get_hill_score` — capacidad en subidas y potencia

### Performance y proyección
- `garmin_get_max_metrics` — VO2max de running y ciclismo, fitness age
- `garmin_get_race_predictions` — tiempos predichos para 5K, 10K, media y maratón
- `garmin_get_lactate_threshold` — ritmo y FC en el umbral de lactato
- `garmin_get_cycling_ftp` — FTP en watts
- `garmin_get_personal_records` — records personales registrados en Garmin

### Actividades
- `garmin_get_activities` — últimas N actividades de Garmin
- `strava_get_activities` — últimas N actividades de Strava
- `strava_get_activity_detail` — detalle completo de una actividad por ID
- `strava_get_athlete_stats` — totales acumulados del atleta

### Workouts (crear y agendar en Garmin)
- `garmin_schedule_easy_run` — rodaje suave Z2
- `garmin_schedule_tempo_run` — tempo continuo en Z4
- `garmin_schedule_interval_run` — intervalos por distancia (ej: 4x1000m)
- `garmin_schedule_long_run` — tirada larga Z2 con bloque final en Z3
- `garmin_schedule_easy_bike` — rodaje suave de ciclismo Z2
- `garmin_get_scheduled_workouts` — workouts ya agendados en el calendario
- `garmin_delete_scheduled_workout` — borra un workout del calendario

---

## Setup completo paso a paso

### Paso 1 — Conseguir credenciales de Strava

1. Entrá a https://www.strava.com/settings/api y creá una app (website: `http://localhost`).
2. Anotá el **Client ID** y el **Client Secret**.
3. Abrí esta URL en el navegador (reemplazando `TU_CLIENT_ID`):
   ```
   https://www.strava.com/oauth/authorize?client_id=TU_CLIENT_ID&redirect_uri=http://localhost&response_type=code&scope=activity:read_all,profile:read_all
   ```
4. Autorizá en Strava. La URL de redirección va a fallar visualmente — copiá el valor de `code` de la barra de direcciones.
5. En PowerShell (Windows), ejecutá:
   ```
   curl.exe -X POST https://www.strava.com/oauth/token -d client_id=TU_CLIENT_ID -d client_secret=TU_CLIENT_SECRET -d code=EL_CODE -d grant_type=authorization_code
   ```
6. Copiá el `refresh_token` de la respuesta.

### Paso 2 — Subir el código a GitHub

1. Creá un repositorio **privado** en github.com.
2. Subí todos los archivos del proyecto (los que empiezan con punto como `.gitignore` y `.python-version` creálos manualmente en GitHub con "Create new file").
3. **Nunca subas el archivo `.env`** con tus credenciales reales.

### Paso 3 — Deploy en Railway

1. Entrá a https://railway.app y logueate con GitHub.
2. "New Project" → "Deploy from GitHub repo" → seleccioná este repo.
3. En la pestaña **Variables**, agregá una por una:

| Variable | Valor |
|---|---|
| `GARMIN_EMAIL` | Tu email de Garmin Connect |
| `GARMIN_PASSWORD` | Tu contraseña de Garmin Connect |
| `STRAVA_CLIENT_ID` | El de strava.com/settings/api |
| `STRAVA_CLIENT_SECRET` | Ídem |
| `STRAVA_REFRESH_TOKEN` | El que conseguiste en el paso 1 |
| `OWNER_USERNAME` | Un usuario que vos elijas (no es el de Garmin) |
| `OWNER_PASSWORD` | Una contraseña que vos elijas |
| `SERVER_URL` | La URL pública de Railway (ver paso 4) |

4. En **Settings → Networking**, generá un dominio público. Copiá esa URL (ej: `https://tu-app.up.railway.app`) y pegála como valor de `SERVER_URL`.

### Paso 4 — Conectar con Claude.ai

1. En Claude.ai → Settings → Connectors → "Add custom connector".
2. URL: `https://tu-app.up.railway.app/mcp`
3. Dejá **vacío** el campo de OAuth Client ID si aparece (es importante, no escribas nada ahí).
4. Claude.ai te redirige a una pantalla de login — ingresás el `OWNER_USERNAME` y `OWNER_PASSWORD` que configuraste en Railway.
5. Listo. El token dura 8 horas y se renueva automáticamente.

> **Nota:** si Railway reinicia el servicio, los tokens se pierden (viven en memoria) y vas a tener que volver a loguearte una vez desde Claude.ai. Es el comportamiento esperado.

---

## Probar localmente (opcional)

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Editá .env con tus credenciales reales
python server.py
```

El servidor queda en `http://localhost:8000/mcp`.

---

## Notas de seguridad

- Las credenciales van como variables de entorno en Railway, nunca en el código ni en GitHub.
- El servidor implementa OAuth 2.1 con PKCE. Sin login correcto, cualquier llamada a `/mcp` devuelve 401.
- `garminconnect` es una librería no oficial de la comunidad. Funciona bien, pero si Garmin cambia algo internamente puede requerir actualización.
- El VO2max de ciclismo y el FTP solo aparecen si entrenás con potenciómetro o sensor compatible.
