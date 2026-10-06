"""Opt-in hosted pilot: extension onboarding, passwordless consent, isolated MCP accounts.

This mode never imports the local owner's vault. Browser credentials enter only
through an explicit connection initiated by the user in the companion extension.
"""

import argparse
import asyncio
import html
import os
import re
import secrets
import sys
import time
from collections import OrderedDict, deque
from pathlib import Path

import anyio
import uvicorn
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AuthorizationCode, TokenError, construct_redirect_uri
from starlette.responses import HTMLResponse, JSONResponse

from .auth import HEADERS, SCOPE, OwnerOAuth
from .backend import KeepBackend, quiet_upstream
from .cli import exchange_google_token, public_url
from .credentials import Credentials, SetupError
from .hosted_store import HostedStore, digest, exclusive_state
from .server import build_server, http_app

EXTENSION_ID = "fmpbecffbmodgopadagphiaopjfnoppo"


class AccountBackends:
    def __init__(self, store: HostedStore, factory=KeepBackend):
        self.store, self.factory = store, factory
        self.cache = OrderedDict()

    def for_request(self):
        token = get_access_token()
        if not token or not token.subject:
            raise SetupError("No connected Keep account. Connect using the Keep Context extension.")
        return self.get(token.subject)

    def get(self, identity: str):
        credentials = self.store.credentials(identity)
        if identity not in self.cache:
            self.cache[identity] = self.factory(credentials)
        self.cache.move_to_end(identity)
        while len(self.cache) > 20:
            self.cache.popitem(last=False)
        return self.cache[identity]


class HostedOAuth(OwnerOAuth):
    def __init__(self, base: str, store: HostedStore, redirect_uris=()):
        self.store = store
        # The inherited password form is never reachable in this mode. Keep the
        # existing provider's tested DCR/PKCE/token lifecycle, with SDK subjects.
        super().__init__(base, secrets.token_urlsafe(32), redirect_uris, state=store)

    def reload(self):
        stored = self.store.load()
        from mcp.server.auth.provider import AccessToken, RefreshToken
        from mcp.shared.auth import OAuthClientInformationFull

        for name, model in (
            ("clients", OAuthClientInformationFull),
            ("access", AccessToken),
            ("refresh", RefreshToken),
        ):
            setattr(
                self, name, {k: model.model_validate(v) for k, v in stored.get(name, {}).items()}
            )
        self.pairs = stored.get("pairs", {})

    async def load_access_token(self, token):
        result = await super().load_access_token(token)
        return result if result and result.subject in self.store.data["accounts"] else None

    async def exchange_authorization_code(self, client, authorization_code):
        if authorization_code.subject not in self.store.data["accounts"]:
            raise TokenError("invalid_grant", "Keep account disconnected. Connect again.")
        return await super().exchange_authorization_code(client, authorization_code)

    async def exchange_refresh_token(self, client, refresh_token, scopes):
        if refresh_token.subject not in self.store.data["accounts"]:
            raise TokenError("invalid_grant", "Keep account disconnected. Connect again.")
        return await super().exchange_refresh_token(client, refresh_token, scopes)

    def details(self, ticket: str):
        self._prune()
        pending = self.pending.get(ticket)
        if not pending or pending.expires <= time.time():
            raise SetupError("This connection link expired. Start Connect again in ChatGPT.")
        return pending

    def decide(self, ticket: str, identity: str, action: str) -> str:
        pending = self.details(ticket)
        self.pending.pop(ticket)
        if action == "cancel":
            return construct_redirect_uri(
                str(pending.params.redirect_uri), error="access_denied", state=pending.params.state
            )
        code = secrets.token_urlsafe(32)
        self.codes[code] = AuthorizationCode(
            code=code,
            client_id=pending.client_id,
            scopes=[SCOPE],
            subject=identity,
            expires_at=time.time() + 60,
            code_challenge=pending.params.code_challenge,
            redirect_uri=pending.params.redirect_uri,
            redirect_uri_provided_explicitly=pending.params.redirect_uri_provided_explicitly,
            resource=self.resource,
        )
        return construct_redirect_uri(
            str(pending.params.redirect_uri), code=code, state=pending.params.state
        )

    async def consent(self, request):
        self._prune()
        ticket = request.query_params.get("ticket", "")
        pending = self.pending.get(ticket)
        if pending and pending.expires <= time.time():
            return self._deny(ticket, pending, "Connection expired. Please connect again.")
        if not pending:
            return page(
                "Start a fresh connection",
                "This link is no longer available. Return to ChatGPT and choose Connect again.",
                status=400,
            )
        if request.method == "POST":
            form = await request.form()
            if form.get("action") == "cancel" and secrets.compare_digest(
                str(form.get("csrf", "")), pending.csrf
            ):
                return self._deny(ticket, pending, "Connection cancelled.")
            return page("Use the extension", "Approve from the Keep Context extension.", status=403)
        return page(
            "One last click",
            "Open the Keep Context extension in your browser toolbar. "
            "Check the Google account, then click Allow ChatGPT. No password needed.",
            extra=f'<form method="post"><input type="hidden" name="csrf" '
            f'value="{pending.csrf}"><button name="action" value="cancel">'
            "Cancel and return to ChatGPT</button></form>",
            headers=self._consent_headers(pending),
        )


def page(title: str, message: str, extra: str = "", status=200, headers=None):
    return HTMLResponse(
        f"""<!doctype html><html lang="en"><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>Keep Context</title>
    <style>body{{font:17px/1.6 system-ui;background:#f7f6f2;color:#252820;
    max-width:520px;margin:10vh auto;padding:24px}}h1{{font:36px Georgia}}main{{background:white;
    padding:32px;border:1px solid #deded5;border-radius:20px}}button,a{{font:inherit}}
    button{{padding:12px;margin-top:16px;cursor:pointer}}a{{color:#3c542e}}</style>
    <main><p>KEEP CONTEXT</p><h1>{html.escape(title)}</h1><p>{html.escape(message)}</p>{extra}
    <p><a href="https://chatgpt.com/plugins">Return to ChatGPT</a></p></main></html>""",
        status_code=status,
        headers=headers or HEADERS,
    )


class Pilot:
    def __init__(
        self,
        base: str,
        store: HostedStore,
        factory=KeepBackend,
        exchange=exchange_google_token,
        extension_id=EXTENSION_ID,
        enrollment_code: str = "",
        open_enrollment=False,
        redirect_uris=(),
    ):
        if not re.fullmatch(r"[a-p]{32}", extension_id):
            raise SetupError("Configure a valid Chrome extension ID.")
        self.base, self.store, self.exchange = base, store, exchange
        self.extension_origin = "chrome-extension://" + extension_id
        self.enrollment_code, self.open_enrollment = enrollment_code, open_enrollment
        self.backends = AccountBackends(store, factory)
        self.oauth = HostedOAuth(base, store, redirect_uris)
        self.attempts = deque(maxlen=12)
        self.busy = False
        self.jobs = {}
        self.tasks = set()

    async def api(self, request):
        origin = request.headers.get("origin")
        cors = {"Access-Control-Allow-Origin": self.extension_origin, "Vary": "Origin"}
        if origin and origin != self.extension_origin:
            return JSONResponse({"error": "Use the Keep Context extension."}, 403, headers=HEADERS)
        headers = {**HEADERS, **cors}
        if request.method == "OPTIONS":
            return JSONResponse(
                {},
                headers={
                    **headers,
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Authorization, Content-Type",
                },
            )
        try:
            payload = await request.json() if request.method == "POST" else {}
            if not isinstance(payload, dict):
                raise SetupError("Invalid request. Try again from the extension.")
            route = request.url.path
            if route == "/api/config":
                result = {
                    "mcp_url": self.base + "/mcp",
                    "invitation_required": not self.open_enrollment,
                    "extension_id": self.extension_origin.split("//")[1],
                }
            elif route == "/api/connect":
                result = await self.connect(payload)
            elif route == "/api/progress":
                device_key = request.headers.get("authorization", "").removeprefix("Bearer ")
                identity = self.store.owner(device_key)
                if identity:
                    result = {
                        "status": "connected",
                        "email": self.store.credentials(identity).email,
                    }
                else:
                    result = self.jobs.get(
                        digest(device_key),
                        {"status": "idle", "error": "Start a fresh Google connection."},
                    )
            else:
                identity = self.store.owner(
                    request.headers.get("authorization", "").removeprefix("Bearer ")
                )
                if not identity:
                    return JSONResponse(
                        {"error": "Open the extension and connect Google Keep."},
                        401,
                        headers=headers,
                    )
                if route == "/api/account":
                    result = {
                        "email": self.store.credentials(identity).email,
                        "mcp_url": self.base + "/mcp",
                    }
                elif route == "/api/disconnect":
                    self.store.delete(identity)
                    for mapping in (self.oauth.codes, self.oauth.access, self.oauth.refresh):
                        for key in list(mapping):
                            if mapping[key].subject == identity:
                                mapping.pop(key)
                    self.oauth._prune()
                    self.oauth._save()
                    self.backends.cache.pop(identity, None)
                    result = {"disconnected": True}
                elif route in ("/api/pending", "/api/approve"):
                    ticket = str(payload.get("ticket", ""))
                    pending = self.oauth.details(ticket)
                    if route == "/api/pending":
                        result = {
                            "client": self.oauth.clients[pending.client_id].client_name,
                            "callback": str(pending.params.redirect_uri),
                            "scope": SCOPE,
                            "email": self.store.credentials(identity).email,
                        }
                    else:
                        action = payload.get("action")
                        if action not in ("allow", "cancel"):
                            raise SetupError("Choose Allow or Cancel.")
                        result = {"redirect_url": self.oauth.decide(ticket, identity, action)}
                else:
                    return JSONResponse({"error": "Not found."}, 404, headers=headers)
            return JSONResponse(result, headers=headers)
        except SetupError as error:
            return JSONResponse({"error": str(error)}, 400, headers=headers)
        except Exception:
            # Never let ASGI traceback logging include an upstream secret/response.
            return JSONResponse(
                {"error": "Connection could not finish. Retry from the extension."},
                503,
                headers=headers,
            )

    async def connect(self, payload):
        device_key = payload.get("device_key", "")
        if not isinstance(device_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", device_key):
            raise SetupError("Invalid connection session. Reopen the extension.")
        # A lost response can be recovered with the same locally saved device key.
        identity = self.store.owner(device_key)
        if identity:
            return {"status": "connected", "email": self.store.credentials(identity).email}
        job_key = digest(device_key)
        if self.jobs.get(job_key, {}).get("status") == "connecting":
            return {"status": "connecting"}
        if not self.open_enrollment and (
            not self.enrollment_code
            or not secrets.compare_digest(str(payload.get("invitation", "")), self.enrollment_code)
        ):
            raise SetupError("Enter your invitation code before connecting.")
        if len(self.store.data["accounts"]) >= self.store.max_accounts:
            raise SetupError("This pilot is full. Contact the host for an invitation.")
        now = time.monotonic()
        while self.attempts and self.attempts[0] < now - 60:
            self.attempts.popleft()
        if self.busy or len(self.attempts) >= 12:
            raise SetupError("Another connection is finishing. Wait a minute and try again.")
        self.attempts.append(now)
        email, cookie = payload.get("email", ""), payload.get("cookie", "")
        if not isinstance(email, str) or not re.fullmatch(r"[^\s@]{1,150}@[^\s@]{1,100}", email):
            raise SetupError("Enter the Google email you will sign in with.")
        if not isinstance(cookie, str):
            raise SetupError("Sign in to Google again, then finish the connection.")
        self.busy = True
        self.jobs = {k: j for k, j in self.jobs.items() if j.get("started", 0) > now - 1800}
        self.jobs[job_key] = {"status": "connecting", "started": now}
        task = asyncio.create_task(self.verify(email, cookie, device_key, job_key))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return {"status": "connecting"}

    async def verify(self, email, cookie, device_key, job_key):
        # MV3 workers can stop when a fetch takes >30s. Complete Google verification
        # independently, then let the extension poll by its previously saved secret.
        try:

            def verify():
                android_id = secrets.token_hex(8)
                master = self.exchange(email, cookie, android_id)
                credentials = Credentials(email, master, android_id)
                backend = self.backends.factory(credentials)
                notes = backend.snapshot()
                return credentials, backend, sum(not n.trashed for n in notes)

            credentials, _, count = await anyio.to_thread.run_sync(verify)
            identity = self.store.enroll(credentials, device_key)
            self.oauth.reload()
            # Invalidate unexchanged codes for any previous connection to this account.
            self.oauth.codes = {k: c for k, c in self.oauth.codes.items() if c.subject != identity}
            self.backends.cache.pop(identity, None)
            self.jobs[job_key] = {
                "status": "connected",
                "email": credentials.email,
                "note_count": count,
                "started": time.monotonic(),
            }
        except SetupError as error:
            message = str(error)
            if "MissingDroidguard" in message:
                message = (
                    "Google requires device verification this connection cannot provide. "
                    "Contact the host."
                )
            elif "cookie" in message or "token exchange" in message:
                message = (
                    "Google couldn't finish sign-in. Click Connect Google Keep to sign in again."
                )
            self.jobs[job_key] = {
                "status": "failed",
                "error": message,
                "started": time.monotonic(),
            }
        except Exception:
            self.jobs[job_key] = {
                "status": "failed",
                "error": "Could not connect. Sign in again.",
                "started": time.monotonic(),
            }
        finally:
            self.busy = False

    def app(self, port=8800):
        server = build_server(self.backends, self.oauth, port)
        for route, methods in (
            ("config", ["GET", "OPTIONS"]),
            ("connect", ["POST", "OPTIONS"]),
            ("account", ["GET", "OPTIONS"]),
            ("progress", ["GET", "OPTIONS"]),
            ("disconnect", ["POST", "OPTIONS"]),
            ("pending", ["POST", "OPTIONS"]),
            ("approve", ["POST", "OPTIONS"]),
        ):
            server.custom_route("/api/" + route, methods=methods)(self.api)
        return http_app(server, self.oauth)


def main():
    quiet_upstream()
    parser = argparse.ArgumentParser(description="Run the isolated hosted Keep Context pilot.")
    parser.add_argument(
        "--public-url",
        default=os.environ.get("KEEP_PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL"),
    )
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8800")))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--state-file", type=Path, default=Path(".keep-context/hosted.enc"))
    parser.add_argument("--open-enrollment", action="store_true")
    args = parser.parse_args()
    try:
        base = public_url(args.public_url or "")
        if not 1 <= args.port <= 65535:
            raise SetupError("Choose a valid port.")
        key = os.environ.get("KEEP_HOSTED_KEY", "")
        with exclusive_state(args.state_file):
            store = HostedStore(args.state_file, key, base + "/mcp")
            pilot = Pilot(
                base,
                store,
                extension_id=os.environ.get("KEEP_EXTENSION_ID", EXTENSION_ID),
                enrollment_code=os.environ.get("KEEP_ENROLLMENT_CODE", ""),
                open_enrollment=args.open_enrollment,
            )
            uvicorn.run(
                pilot.app(args.port),
                host=args.host,
                port=args.port,
                log_level="critical",
                access_log=False,
            )
    except (SetupError, ValueError):
        print(
            "Hosted setup could not start. Check the public URL, encryption key and state file.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
