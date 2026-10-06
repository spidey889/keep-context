"""Single-owner OAuth provider; the official SDK handles discovery, DCR and PKCE.

Google's account-wide master token never crosses this boundary. Opaque MCP tokens
only grant read access to this server, with a specific resource and expiry.
"""

import hashlib
import html
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from .state import EncryptedState

SCOPE = "keep:read"
HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
    "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
}


@dataclass
class Pending:
    client_id: str
    params: AuthorizationParams
    expires: float
    csrf: str


class OwnerOAuth(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    def __init__(
        self,
        base_url: str,
        password: str,
        redirect_uris: tuple[str, ...] = (),
        state: EncryptedState | None = None,
    ):
        if len(password) < 20:
            raise ValueError("Choose a connection password of at least 20 characters.")
        self.base_url = base_url.rstrip("/")
        self.resource = self.base_url + "/mcp"
        self.redirect_uris = redirect_uris
        self.salt = secrets.token_bytes(16)
        self.password_hash = self._hash(password)
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.pending: dict[str, Pending] = {}
        self.codes: dict[str, AuthorizationCode] = {}
        self.access: dict[str, AccessToken] = {}
        self.refresh: dict[str, RefreshToken] = {}
        self.pairs: dict[str, str] = {}
        self.failures: list[float] = []
        self.state = state
        if state:
            stored = state.load()
            if stored.get("resource", self.resource) != self.resource:
                raise ValueError(
                    "Public URL changed. Start with --reset-access and reconnect ChatGPT."
                )
            self.clients = {
                k: OAuthClientInformationFull.model_validate(v)
                for k, v in stored.get("clients", {}).items()
            }
            self.access = {
                k: AccessToken.model_validate(v) for k, v in stored.get("access", {}).items()
            }
            self.refresh = {
                k: RefreshToken.model_validate(v) for k, v in stored.get("refresh", {}).items()
            }
            self.pairs = stored.get("pairs", {})
            self._prune()

    def _save(self):
        if self.state:
            self.state.save(
                {
                    "resource": self.resource,
                    "pairs": self.pairs,
                    **{
                        name: {k: v.model_dump(mode="json") for k, v in mapping.items()}
                        for name, mapping in (
                            ("clients", self.clients),
                            ("access", self.access),
                            ("refresh", self.refresh),
                        )
                    },
                }
            )

    def _hash(self, password: str) -> bytes:
        return hashlib.scrypt(password.encode(), salt=self.salt, n=16384, r=8, p=1)

    def _prune(self):
        now = time.time()
        self.pending = {k: v for k, v in self.pending.items() if v.expires > now}
        for mapping in (self.codes, self.access, self.refresh):
            for key in list(mapping):
                if mapping[key].expires_at is not None and mapping[key].expires_at <= now:
                    mapping.pop(key)
        self.pairs = {a: r for a, r in self.pairs.items() if a in self.access or r in self.refresh}
        self.failures = [t for t in self.failures if t > now - 60]

    def allowed_redirect(self, uri: str) -> bool:
        if uri in self.redirect_uris:
            return True
        parsed = urlparse(uri)
        return (
            parsed.scheme == "https"
            and parsed.netloc == "chatgpt.com"
            and not parsed.query
            and not parsed.fragment
            and (
                parsed.path == "/connector_platform_oauth_redirect"
                or parsed.path.startswith("/connector/oauth/")
                and bool(parsed.path.removeprefix("/connector/oauth/"))
            )
        )

    async def get_client(self, client_id):
        return self.clients.get(client_id)

    async def register_client(self, client_info):
        if not client_info.redirect_uris or any(
            not self.allowed_redirect(str(uri)) for uri in client_info.redirect_uris
        ):
            raise RegistrationError(
                "invalid_redirect_uri",
                "Only ChatGPT or explicitly allowed callback URLs are accepted.",
            )
        if len(self.clients) >= 128:
            raise RegistrationError(
                "invalid_client_metadata", "Client limit reached. Restart server."
            )
        self.clients[client_info.client_id] = client_info
        self._save()

    async def authorize(self, client, params):
        self._prune()
        if params.resource != self.resource:
            # SDK 1.30's authorize handler does not serialize invalid_target yet.
            raise AuthorizeError("invalid_request", "Request the advertised MCP resource.")
        if params.scopes != [SCOPE]:
            raise AuthorizeError("invalid_scope", "Only keep:read is supported.")
        if len(self.pending) >= 128:
            raise AuthorizeError(
                "temporarily_unavailable", "Too many pending sign-ins. Retry later."
            )
        ticket = secrets.token_urlsafe(32)
        self.pending[ticket] = Pending(
            client.client_id, params, time.time() + 300, secrets.token_urlsafe(32)
        )
        return self.base_url + "/connect?ticket=" + ticket

    async def consent(self, request: Request) -> Response:
        self._prune()
        ticket = request.query_params.get("ticket", "")
        pending = self.pending.get(ticket)
        if pending is None:
            return HTMLResponse(
                "Sign-in expired. Start the connection again in ChatGPT.",
                status_code=400,
                headers=HEADERS,
            )
        if request.method == "POST":
            if len(self.failures) >= 5:
                return HTMLResponse(
                    "Too many attempts. Wait one minute and try again.",
                    status_code=429,
                    headers={**HEADERS, "Retry-After": "60"},
                )
            form = await request.form()
            csrf = str(form.get("csrf", ""))
            password = str(form.get("password", ""))
            if (
                not secrets.compare_digest(csrf, pending.csrf)
                or len(password) > 1024
                or not secrets.compare_digest(self._hash(password), self.password_hash)
            ):
                self.failures.append(time.time())
                return HTMLResponse(
                    "Sign-in failed. Go back and try your connection password again.",
                    status_code=403,
                    headers=HEADERS,
                )
            self.pending.pop(ticket)
            code = secrets.token_urlsafe(32)
            params = pending.params
            self.codes[code] = AuthorizationCode(
                code=code,
                client_id=pending.client_id,
                scopes=[SCOPE],
                expires_at=time.time() + 60,
                code_challenge=params.code_challenge,
                redirect_uri=params.redirect_uri,
                redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
                resource=self.resource,
            )
            return RedirectResponse(
                construct_redirect_uri(str(params.redirect_uri), code=code, state=params.state),
                status_code=303,
                headers=HEADERS,
            )
        client = self.clients[pending.client_id]
        name = html.escape(client.client_name or "MCP client")
        content = f"""<!doctype html><html lang="en"><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Connect Keep Context</title><style>
        body{{font:17px system-ui;margin:8vh auto;padding:24px;max-width:480px;
        background:#f6f7f9;color:#17202a}} main{{background:white;padding:32px;border-radius:16px}}
        input,button{{box-sizing:border-box;width:100%;padding:12px;font:inherit;margin-top:12px}}
        button{{background:#185abc;color:white;border:0;border-radius:8px;cursor:pointer}}
        small{{color:#536170}}</style><main><h1>Connect your notes</h1>
        <p>Allow <strong>{name}</strong> to search and read the Google Keep account connected
        to this server. This includes archived notes. It cannot edit or delete notes.</p>
        <form method="post"><input type="hidden" name="csrf" value="{pending.csrf}">
        <label for="password">Keep Context connection password</label>
        <input id="password" name="password" type="password" autocomplete="current-password"
        required maxlength="1024"><button>Allow read access</button></form>
        <p><small>Use the separate password you chose during setup. Never enter your Google
        password or Google token here.</small></p></main></html>"""
        return HTMLResponse(content, headers=HEADERS)

    async def load_authorization_code(self, client, authorization_code):
        self._prune()
        code = self.codes.get(authorization_code)
        return code if code and code.client_id == client.client_id else None

    def _issue(self, client_id: str, scopes: list[str]) -> OAuthToken:
        self._prune()
        if len(self.refresh) >= 128:
            raise TokenError("invalid_grant", "Connection limit reached. Restart server.")
        now = int(time.time())
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.access[access] = AccessToken(
            token=access,
            client_id=client_id,
            scopes=scopes,
            expires_at=now + 3600,
            resource=self.resource,
        )
        self.refresh[refresh] = RefreshToken(
            token=refresh, client_id=client_id, scopes=scopes, expires_at=now + 30 * 86400
        )
        self.pairs[access] = refresh
        self._save()
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=3600,
            refresh_token=refresh,
            scope=" ".join(scopes),
        )

    async def exchange_authorization_code(self, client, authorization_code):
        if self.codes.pop(authorization_code.code, None) is None:
            raise TokenError("invalid_grant", "Authorization code was already used.")
        return self._issue(client.client_id, authorization_code.scopes)

    async def load_refresh_token(self, client, refresh_token):
        self._prune()
        token = self.refresh.get(refresh_token)
        return token if token and token.client_id == client.client_id else None

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        if self.refresh.get(refresh_token.token) is None:
            raise TokenError("invalid_grant", "Refresh token was already used.")
        await self.revoke_token(refresh_token)
        return self._issue(client.client_id, scopes)

    async def load_access_token(self, token):
        self._prune()
        return self.access.get(token)

    async def revoke_token(self, token):
        for access, refresh in list(self.pairs.items()):
            if token.token in (access, refresh):
                self.access.pop(access, None)
                self.refresh.pop(refresh, None)
                self.pairs.pop(access, None)
        self._save()
