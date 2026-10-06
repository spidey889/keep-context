"""Opt-in real HTTPS/OAuth/MCP smoke with demo notes; no browser or Google account.

Run: uv run python scripts/smoke_https.py
Requires cloudflared on PATH. Both processes stop when the smoke finishes.
"""

import asyncio
import base64
import hashlib
import re
import socket
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlparse

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from keep_context.tunnel import open_tunnel


def main():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with open_tunnel(port) as base:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "keep_context.cli",
                "serve",
                "--demo",
                "--port",
                str(port),
                "--public-url",
                base,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            with httpx.Client(base_url=base, timeout=15) as client:
                for _ in range(15):
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(1)
                else:
                    raise RuntimeError("Public HTTPS health check did not succeed")
                assert (
                    client.post(
                        "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
                    ).status_code
                    == 401
                )
                resource = base + "/mcp"
                callback = "https://chatgpt.com/connector_platform_oauth_redirect"
                registered = client.post(
                    "/register",
                    json={
                        "client_name": "Keep Context HTTPS smoke",
                        "redirect_uris": [callback],
                        "grant_types": ["authorization_code", "refresh_token"],
                        "response_types": ["code"],
                    },
                )
                registered.raise_for_status()
                info = registered.json()
                verifier = "a" * 64
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                authorization = client.get(
                    "/authorize",
                    params={
                        "client_id": info["client_id"],
                        "redirect_uri": callback,
                        "response_type": "code",
                        "scope": "keep:read",
                        "resource": resource,
                        "code_challenge": challenge.decode().rstrip("="),
                        "code_challenge_method": "S256",
                        "state": "demo-smoke",
                    },
                )
                assert authorization.status_code == 302
                location = authorization.headers["location"]
                consent = client.get(location)
                csrf = re.search(r'name="csrf" value="([^"]+)"', consent.text).group(1)
                approved = client.post(
                    location, data={"csrf": csrf, "password": "demo-only-no-google-account"}
                )
                assert approved.status_code == 303
                params = parse_qs(urlparse(approved.headers["location"]).query)
                assert params["state"] == ["demo-smoke"]
                tokens = client.post(
                    "/token",
                    data={
                        "client_id": info["client_id"],
                        "client_secret": info["client_secret"],
                        "grant_type": "authorization_code",
                        "code": params["code"][0],
                        "redirect_uri": callback,
                        "code_verifier": verifier,
                        "resource": resource,
                    },
                )
                tokens.raise_for_status()
                token = tokens.json()["access_token"]

            async def verify():
                async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token}) as http:
                    async with streamable_http_client(resource, http_client=http) as (
                        read,
                        write,
                        _,
                    ):
                        async with ClientSession(read, write) as session:
                            await session.initialize()
                            assert len((await session.list_tools()).tools) == 5
                            cases = [
                                ("search", {"query": "Garden plan"}),
                                ("fetch", {"id": "demo-trip"}),
                                ("list_recent_notes", {}),
                                ("list_labels", {}),
                                ("find_tasks", {}),
                            ]
                            for name, arguments in cases:
                                result = await session.call_tool(name, arguments)
                                assert not result.isError and result.structuredContent
                                if name == "search":
                                    assert result.structuredContent["total"] == 1
                                if name == "fetch":
                                    assert "- [x] Pack a bag" in result.structuredContent["text"]
                print(
                    "PASS: public HTTPS, denied anonymous access, confidential DCR, consent, "
                    "PKCE, official MCP initialization and all five tools (demo data)."
                )

            asyncio.run(verify())
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
