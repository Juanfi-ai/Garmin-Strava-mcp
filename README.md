# Garmin + Strava MCP Server

Servidor MCP que le da a Claude acceso en tiempo real a tus datos de
Garmin Connect (sueño, HRV, body battery, training readiness, actividades)
y de Strava (actividades, estadisticas), para que pueda analizar tu
entrenamiento y proponerte sesiones.

## Que hace cada archivo

- `garmin_client.py` — habla con Garmin Connect (libreria no oficial, usa tu usuario/contraseña).
- `strava_client.py` — habla con la API oficial de Strava (OAuth2).
- `server.py` — servidor MCP que expone ambos como herramientas + autenticacion por token.
- `requirements.txt` — dependencias exactas.
- `.env.example` — plantilla de variables de entorno (NUNCA subir el `.env` real a GitHub).

## Paso 1 — Conseguir credenciales de Strava

Esto es probablemente donde te trabaste con el conector original.

1. Entra a https://www.strava.com/settings/api
2. Crea una "My API Application" (poné cualquier nombre, website podes poner `http://localhost`).
3. Anota el **Client ID** y el **Client Secret** que te muestra.
4. Authorization Callback Domain: poné `localhost` (no importa mucho para este uso).
5. Ahora necesitas un **refresh token**. Para conseguirlo:
   - Abrí esta URL en el navegador, reemplazando `TU_CLIENT_ID`:
     ```
     https://www.strava.com/oauth/authorize?client_id=TU_CLIENT_ID&redirect_uri=http://localhost&response_type=code&scope=activity:read_all,profile:read_all
     ```
   - Strava te va a pedir autorizar. Aceptá.
   - Te redirige a una URL tipo `http://localhost/?state=&code=ABC123&scope=...`. Copiá el valor de `code`.
   - Con ese `code`, ejecutá este comando (reemplazando los valores):
     ```bash
     curl -X POST https://www.strava.com/oauth/token \
       -d client_id=TU_CLIENT_ID \
       -d client_secret=TU_CLIENT_SECRET \
       -d code=EL_CODE_QUE_COPIASTE \
       -d grant_type=authorization_code
     ```
   - La respuesta trae un `refresh_token`. Ese es el que vas a usar (no expira, podes usarlo siempre para pedir nuevos access tokens).

## Paso 2 — Probar localmente (opcional)

```bash
python -m venv venv
source venv/bin/activate  # en Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Editar .env con tus credenciales reales
python server.py
```

Si todo anda bien, va a quedar escuchando en `http://localhost:8000/mcp`.

## Paso 3 — Subir a GitHub

```bash
git init
git add .
git commit -m "Servidor MCP Garmin + Strava"
# Crear un repo nuevo en github.com (privado, recomendado) y luego:
git remote add origin https://github.com/TU_USUARIO/garmin-strava-mcp.git
git branch -M main
git push -u origin main
```

Importante: el `.gitignore` ya excluye `.env`, asi que tus credenciales reales
NUNCA se suben a GitHub. Eso es justamente el punto de usar variables de entorno.

## Paso 4 — Deploy en Railway

1. Entra a https://railway.app y logueate con GitHub.
2. "New Project" → "Deploy from GitHub repo" → elegi este repo.
3. Railway va a detectar que es Python y va a intentar levantarlo solo.
4. Ve a la pestaña "Variables" del proyecto y agrega, una por una:
   - `GARMIN_EMAIL`
   - `GARMIN_PASSWORD`
   - `STRAVA_CLIENT_ID`
   - `STRAVA_CLIENT_SECRET`
   - `STRAVA_REFRESH_TOKEN`
   - `MCP_AUTH_TOKEN` (inventate un string largo y random, por ejemplo con `openssl rand -hex 32`)
5. Railway redeploya solo al guardar las variables.
6. En la pestaña "Settings" → "Networking", generá un dominio publico
   (botón "Generate Domain"). Te va a dar algo como
   `https://garmin-strava-mcp-production.up.railway.app`.

## Paso 5 — Conectar con Claude.ai

1. En Claude.ai, ve a Settings → Connectors → "Add custom connector".
2. URL del servidor: `https://TU-DOMINIO-DE-RAILWAY.up.railway.app/mcp`
3. Si te pide headers de autenticacion, agregá:
   - Header: `Authorization`
   - Valor: `Bearer TU_MCP_AUTH_TOKEN` (el mismo valor que pusiste en Railway)
4. Guardá y probá pidiendole a Claude que liste tus actividades recientes.

## Herramientas disponibles

| Herramienta | Que devuelve |
|---|---|
| `garmin_get_sleep` | Sueño: horas, fases, sleep score, HRV nocturno, FC reposo |
| `garmin_get_hrv` | HRV diario, estado, rango base |
| `garmin_get_body_battery` | Energia acumulada/gastada |
| `garmin_get_training_readiness` | Puntaje de preparacion para entrenar hoy |
| `garmin_get_training_status` | Estado de carga (productive/overreaching/etc) |
| `garmin_get_activities` | Actividades recientes de Garmin |
| `strava_get_activities` | Actividades recientes de Strava |
| `strava_get_activity_detail` | Detalle de una actividad puntual |
| `strava_get_athlete_stats` | Totales acumulados del atleta |

## Notas de seguridad

- Tu password de Garmin queda como variable de entorno en Railway, nunca en el codigo ni en GitHub.
- El servidor exige un Bearer token (`MCP_AUTH_TOKEN`) en cada request — sin el token correcto, cualquier llamada devuelve 401. Esto evita que alguien con la URL del servidor pueda leer tus datos.
- `garminconnect` es una libreria de la comunidad, no oficial de Garmin. Funciona bien hoy, pero si Garmin cambia algo internamente puede dejar de andar hasta que se actualice la libreria.
