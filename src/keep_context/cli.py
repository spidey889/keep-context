"""Hidden-input account setup and one-command server startup."""

import argparse
import getpass
import json
import os
import re
import secrets
import sys
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import urlparse

import gpsoauth
import uvicorn

from .auth import OwnerOAuth
from .backend import DemoBackend, KeepBackend, quiet_upstream
from .credentials import (
    Credentials,
    SetupError,
    clear_pending_credentials,
    disconnect,
    load_credentials,
    load_pending_credentials,
    save_credentials,
    save_pending_credentials,
)
from .server import build_server, http_app
from .state import EncryptedState
from .tunnel import open_tunnel


def hidden(prompt: str) -> str:
    if not sys.stdin.isatty():
        raise SetupError("Connect requires an interactive terminal so secrets are never echoed.")
    return getpass.getpass(prompt).strip()


def exchange_google_token(email: str, cookie: str, android_id: str) -> str:
    if (
        not re.fullmatch(r"oauth2_\d+/\S+", cookie)
        or len(cookie) > 8192
        or any(character in cookie for character in "\"';")
    ):
        raise SetupError(
            "Copy only the oauth_token cookie's complete Value, starting with oauth2_ followed "
            "by a number and /. Do not copy its name, an entire row, or another cookie. "
            "No credentials were saved."
        )
    try:
        response = gpsoauth.exchange_token(email, cookie, android_id)
    except Exception:
        raise SetupError(
            "Google token exchange failed. Retry with a fresh oauth_token cookie. "
            "No credentials were saved."
        ) from None
    token = response.get("Token", "")
    if token:
        return token
    # Only fixed, recognized codes are safe to show. Google's other response
    # fields, unknown errors and exception messages can contain credentials/URLs.
    hints = {
        "BadAuthentication": (
            "Google rejected token exchange (BadAuthentication). The cookie may be expired, "
            "already used, incomplete, or from another account. Sign in again through "
            "EmbeddedSetup and paste the fresh cookie promptly."
        ),
        "NeedsBrowser": (
            "Google rejected token exchange (NeedsBrowser). Complete Google's security "
            "check in your browser, then obtain a fresh EmbeddedSetup cookie."
        ),
        "MissingDroidguard": (
            "Google rejected token exchange (MissingDroidguard). Google requires device "
            "verification that this library cannot provide. See docs/AUTHENTICATION.md."
        ),
    }
    code = response.get("Error")
    hint = hints.get(code) if isinstance(code, str) else None
    raise SetupError(
        (hint or "Google rejected token exchange. See docs/AUTHENTICATION.md.")
        + " No credentials were saved."
    )


def connection_password() -> str:
    while True:
        password = hidden("Choose a separate ChatGPT connection password (20+ characters): ")
        if not 20 <= len(password) <= 1024:
            print("Use 20 to 1024 characters. Try again; your Google login is already saved.")
            continue
        if hidden("Confirm connection password: ") != password:
            print("Passwords did not match. Try again; your Google login is already saved.")
            continue
        return password


def connect(use_master_token: bool = False, restart: bool = False) -> None:
    print(
        "Keep Context stores credentials in your OS vault and never asks for your Google password."
    )
    print("Google master tokens have broad account access. Keep this server on a trusted computer.")
    if restart or use_master_token:
        clear_pending_credentials()
    credentials = load_pending_credentials()
    if credentials:
        print("Resuming saved Google setup. No browser login or cookie is needed.")
    else:
        email = input("Google email: ").strip()
        if "@" not in email or len(email) > 254:
            raise SetupError("Enter a valid Google email address.")
        android_id = secrets.token_hex(8)
        if use_master_token:
            token = hidden("Existing Google master token (hidden): ")
        else:
            print("Manually open https://accounts.google.com/EmbeddedSetup and sign in.")
            print(
                "In DevTools > Application/Storage > Cookies > accounts.google.com, "
                "copy oauth_token."
            )
            print("A stuck loading screen can be normal. Paste only into the hidden prompt below.")
            print("Use a fresh cookie promptly; it expires quickly and can be used only once.")
            oauth_token = hidden("oauth_token cookie (hidden): ")
            token = exchange_google_token(email, oauth_token, android_id)
        credentials = Credentials(email, token, android_id)
    print("Verifying read access to Google Keep...")
    notes = KeepBackend(credentials).snapshot()
    save_pending_credentials(credentials)
    print("Google login verified and saved. If interrupted, run connect again to resume.")
    try:
        credentials.connect_password = connection_password()
    except KeyboardInterrupt:
        print("\nSetup paused. Run: uv run keep-context connect (no browser login needed).")
        return
    save_credentials(credentials)
    clear_pending_credentials()
    print(
        f"Connected and verified {sum(not note.trashed for note in notes)} notes. "
        "Credentials saved in the OS vault."
    )


def public_url(value: str) -> str:
    parsed = urlparse(value)
    if (
        parsed.scheme not in ("https", "http")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise SetupError("Public URL must be an origin such as https://keep.example.com (no /mcp).")
    if parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost"):
        raise SetupError("Public connections require HTTPS. HTTP is only allowed on loopback.")
    return value.rstrip("/")


def main() -> None:
    quiet_upstream()
    parser = argparse.ArgumentParser(description="Read Google Keep from ChatGPT through MCP.")
    commands = parser.add_subparsers(dest="command", required=True)
    setup = commands.add_parser(
        "connect", help="Connect Google Keep using hidden prompts and OS vault."
    )
    setup.add_argument("--master-token", action="store_true", help="Use an existing master token.")
    setup.add_argument(
        "--restart", action="store_true", help="Discard saved setup progress and sign in again."
    )
    commands.add_parser("disconnect", help="Delete local OS-vault credentials (stop server first).")
    check = commands.add_parser(
        "doctor", help="Verify connection and count notes without displaying them."
    )
    check.add_argument("--demo", action="store_true")
    serve = commands.add_parser("serve", help="Start the MCP server.")
    serve.add_argument("--transport", choices=["http", "stdio"], default="http")
    serve.add_argument("--public-url", default=os.environ.get("KEEP_PUBLIC_URL"))
    serve.add_argument(
        "--tunnel",
        action="store_true",
        help="Start a temporary public HTTPS Cloudflare tunnel automatically.",
    )
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument(
        "--state-file",
        type=Path,
        default=Path(".keep-context/oauth.enc"),
        help="Encrypted OAuth state (real-account HTTP only). Use a stable path.",
    )
    serve.add_argument(
        "--reset-access",
        action="store_true",
        help="Revoke saved ChatGPT access and recreate OAuth state.",
    )
    serve.add_argument(
        "--demo", action="store_true", help="Use built-in sample notes; never reads Google."
    )
    serve.add_argument(
        "--redirect-uri",
        action="append",
        default=[],
        help="Explicit additional OAuth callback (e.g. MCP Inspector).",
    )
    args = parser.parse_args()
    try:
        if args.command == "connect":
            connect(args.master_token, args.restart)
        elif args.command == "disconnect":
            disconnect()
            print("Removed credentials from the OS vault. Revoke Google's session separately.")
        else:
            credentials = None if args.demo else load_credentials()
            backend = DemoBackend() if args.demo else KeepBackend(credentials)
            if args.command == "doctor":
                notes = backend.snapshot()
                print(
                    json.dumps(
                        {
                            "status": "ok",
                            "mode": "demo" if args.demo else "google",
                            "notes": sum(not n.trashed for n in notes),
                            "synced_at": backend.updated_at,
                        }
                    )
                )
            elif args.transport == "stdio":
                build_server(backend).run(transport="stdio")
            else:
                if not 1 <= args.port <= 65535:
                    raise SetupError("Port must be between 1 and 65535.")
                if args.tunnel and args.public_url:
                    raise SetupError("Use --tunnel or --public-url (including KEEP_PUBLIC_URL).")
                base = public_url(args.public_url or f"http://127.0.0.1:{args.port}")
                password = (
                    "demo-only-no-google-account" if args.demo else credentials.connect_password
                )
                if len(password) < 20:
                    raise SetupError(
                        "Run connect to choose a connection password, or supply "
                        "KEEP_CONNECT_PASSWORD using your deployment secret manager."
                    )
                with ExitStack() as stack:
                    if args.tunnel:
                        base = stack.enter_context(open_tunnel(args.port))
                        # Quick tunnel hostnames change; previous tokens cannot authorize
                        # the new resource. Stable URLs preserve encrypted OAuth state.
                        print(
                            "Temporary URL: recreate the ChatGPT connection after restart.",
                            file=sys.stderr,
                        )
                    if args.reset_access or args.tunnel:
                        args.state_file.unlink(missing_ok=True)
                    state = (
                        None
                        if args.demo
                        else EncryptedState(args.state_file, credentials.master_token)
                    )
                    oauth = OwnerOAuth(base, password, tuple(args.redirect_uri), state=state)
                    server = build_server(backend, oauth, args.port)
                    print(
                        f"Keep Context {'DEMO' if args.demo else 'Google'} MCP: {base}/mcp",
                        file=sys.stderr,
                    )
                    uvicorn.run(
                        http_app(server, oauth),
                        host="127.0.0.1",
                        port=args.port,
                        log_level="warning",
                        access_log=False,
                    )
    except (SetupError, ValueError):
        error = sys.exc_info()[1]
        print(f"Setup: {error}", file=sys.stderr)
        raise SystemExit(1) from None
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
