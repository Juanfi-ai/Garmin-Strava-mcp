"""
Servidor de autorizacion OAuth 2.1 minimo para nuestro MCP server.

Disenado para un unico usuario (vos). En vez de conectar con un proveedor
externo (Google, GitHub, etc), pedimos un usuario/contraseña propios
(definidos por variables de entorno OWNER_USERNAME / OWNER_PASSWORD),
mostramos una pantalla de login simple, y emitimos tokens propios.

Todo el estado (clientes registrados, codigos de autorizacion, tokens)
vive en memoria. Como es un solo usuario y un solo servidor, no hace
falta una base de datos: si el servidor reinicia, Claude.ai vuelve a
pedir login una vez (experiencia normal de cualquier app que cierra sesion).
"""
import os
import time
import secrets
from typing import Optional

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse
from starlette.routing import Route

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    construct_redirect_uri,
)
from mcp.server.auth.provider import TokenError, AuthorizeError
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

ACCESS_TOKEN_TTL_SECONDS = 60 * 60 * 8       # 8 horas
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 365  # 1 año
AUTH_CODE_TTL_SECONDS = 60 * 5               # 5 minutos para completar el login

# Codigos de un solo uso que vinculan una sesion de login HTML con el
# pedido de autorizacion OAuth original (para poder mostrar el form y
# despues retomar el flujo).
_pending_logins: dict[str, AuthorizationParams] = {}
_pending_clients: dict[str, OAuthClientInformationFull] = {}


class SingleUserOAuthProvider(OAuthAuthorizationServerProvider):
    def __init__(self):
        self._clients: dict[str, OAuthClientInformationFull] = {}
        self._auth_codes: dict[str, AuthorizationCode] = {}
        self._access_tokens: dict[str, AccessToken] = {}
        self._refresh_tokens: dict[str, RefreshToken] = {}

    # ---------- Registro de clientes (lo llama Claude.ai automaticamente) ----------

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        return self._clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self._clients[client_info.client_id] = client_info

    # ---------- Paso de autorizacion (pantalla de login) ----------

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        login_id = secrets.token_urlsafe(24)
        _pending_logins[login_id] = params
        _pending_clients[login_id] = client
        return f"/login?login_id={login_id}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> Optional[AuthorizationCode]:
        code = self._auth_codes.get(authorization_code)
        if code and code.expires_at < time.time():
            del self._auth_codes[authorization_code]
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        self._auth_codes.pop(authorization_code.code, None)

        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        now = time.time()

        self._access_tokens[access_token] = AccessToken(
            token=access_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(now + ACCESS_TOKEN_TTL_SECONDS),
        )
        self._refresh_tokens[refresh_token] = RefreshToken(
            token=refresh_token,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=int(now + REFRESH_TOKEN_TTL_SECONDS),
        )

        return OAuthToken(
            access_token=access_token,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            refresh_token=refresh_token,
            scope=" ".join(authorization_code.scopes) if authorization_code.scopes else None,
        )

    # ---------- Refresh tokens ----------

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> Optional[RefreshToken]:
        token = self._refresh_tokens.get(refresh_token)
        if token and token.expires_at and token.expires_at < time.time():
            del self._refresh_tokens[refresh_token]
            return None
        return token

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        # Rotamos ambos tokens (buena practica de seguridad)
        self._refresh_tokens.pop(refresh_token.token, None)

        new_access = secrets.token_urlsafe(32)
        new_refresh = secrets.token_urlsafe(32)
        now = time.time()
        use_scopes = scopes or refresh_token.scopes

        self._access_tokens[new_access] = AccessToken(
            token=new_access,
            client_id=client.client_id,
            scopes=use_scopes,
            expires_at=int(now + ACCESS_TOKEN_TTL_SECONDS),
        )
        self._refresh_tokens[new_refresh] = RefreshToken(
            token=new_refresh,
            client_id=client.client_id,
            scopes=use_scopes,
            expires_at=int(now + REFRESH_TOKEN_TTL_SECONDS),
        )

        return OAuthToken(
            access_token=new_access,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            refresh_token=new_refresh,
            scope=" ".join(use_scopes) if use_scopes else None,
        )

    # ---------- Verificacion de access tokens (se llama en cada tool call) ----------

    async def load_access_token(self, token: str) -> Optional[AccessToken]:
        access = self._access_tokens.get(token)
        if access and access.expires_at and access.expires_at < time.time():
            del self._access_tokens[token]
            return None
        return access

    async def revoke_token(self, token) -> None:
        self._access_tokens.pop(token.token, None)
        self._refresh_tokens.pop(token.token, None)

    # ---------- Helper interno: completar el login y generar el auth code ----------

    def complete_login(self, login_id: str) -> str:
        """Llamado despues de validar usuario/contraseña en /login.
        Genera el authorization_code y devuelve la redirect_uri final hacia Claude.ai."""
        params = _pending_logins.pop(login_id)
        client = _pending_clients.pop(login_id)

        code = secrets.token_urlsafe(32)
        self._auth_codes[code] = AuthorizationCode(
            code=code,
            scopes=params.scopes or [],
            expires_at=time.time() + AUTH_CODE_TTL_SECONDS,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
        )
        return construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state)


provider = SingleUserOAuthProvider()


# ---------- Rutas HTTP propias: pantalla de login ----------

LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Garmin + Strava Coach — Login</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#0f1115; color:#eee;
         display:flex; align-items:center; justify-content:center; height:100vh; margin:0; }}
  form {{ background:#1b1e25; padding:32px; border-radius:12px; width:300px; }}
  h1 {{ font-size:18px; margin-bottom:20px; }}
  input {{ width:100%; padding:10px; margin-bottom:12px; border-radius:6px;
           border:1px solid #333; background:#0f1115; color:#eee; box-sizing:border-box; }}
  button {{ width:100%; padding:10px; border-radius:6px; border:none;
            background:#ff5500; color:white; font-weight:600; cursor:pointer; }}
  .error {{ color:#ff7070; font-size:13px; margin-bottom:12px; }}
</style>
</head>
<body>
  <form method="POST" action="/login">
    <h1>Acceso a tu Coach (Garmin + Strava)</h1>
    {error_html}
    <input type="hidden" name="login_id" value="{login_id}">
    <input type="text" name="username" placeholder="Usuario" autofocus required>
    <input type="password" name="password" placeholder="Contraseña" required>
    <button type="submit">Ingresar</button>
  </form>
</body>
</html>
"""


async def login_get(request: Request):
    login_id = request.query_params.get("login_id", "")
    if login_id not in _pending_logins:
        return HTMLResponse("Sesion de login invalida o expirada. Volve a intentar desde Claude.", status_code=400)
    html = LOGIN_PAGE.format(error_html="", login_id=login_id)
    return HTMLResponse(html)


async def login_post(request: Request):
    form = await request.form()
    login_id = str(form.get("login_id", ""))
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))

    if login_id not in _pending_logins:
        return HTMLResponse("Sesion de login invalida o expirada. Volve a intentar desde Claude.", status_code=400)

    expected_user = os.environ.get("OWNER_USERNAME", "")
    expected_pass = os.environ.get("OWNER_PASSWORD", "")

    if not secrets.compare_digest(username, expected_user) or not secrets.compare_digest(password, expected_pass):
        html = LOGIN_PAGE.format(
            error_html='<div class="error">Usuario o contraseña incorrectos.</div>',
            login_id=login_id,
        )
        return HTMLResponse(html, status_code=401)

    redirect_uri = provider.complete_login(login_id)
    return RedirectResponse(redirect_uri, status_code=302)


login_routes = [
    Route("/login", endpoint=login_get, methods=["GET"]),
    Route("/login", endpoint=login_post, methods=["POST"]),
]
