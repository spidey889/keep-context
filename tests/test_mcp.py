import asyncio
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from test_auth import PASSWORD, approve, exchange, register

from keep_context.backend import DemoBackend
from keep_context.server import build_server


def test_tool_contract_and_mocked_queries(notes):
    backend = DemoBackend()
    backend._notes = notes
    backend.labels.append("Unused")
    server = build_server(backend)

    async def check():
        tools = await server.list_tools()
        assert {t.name for t in tools} == {
            "search",
            "fetch",
            "list_recent_notes",
            "list_labels",
            "find_tasks",
        }
        assert all(t.annotations.readOnlyHint and not t.annotations.destructiveHint for t in tools)
        _, search = await server.call_tool("search", {"query": "VLC", "limit": 2})
        assert search["total"] == 4 and search["next_offset"] == 2
        _, fetched = await server.call_tool("fetch", {"id": "list"})
        assert len(fetched["metadata"]["checklist"]) == 3
        assert "- [x] Buy bread" in fetched["text"]
        _, labels = await server.call_tool("list_labels", {})
        assert {"name": "Unused", "note_count": 0} in labels["labels"]
        assert "Deleted" not in {label["name"] for label in labels["labels"]}
        _, recent = await server.call_tool("list_recent_notes", {"limit": 1})
        assert recent["next_offset"] == 1
        _, tasks = await server.call_tool("find_tasks", {"limit": 1})
        assert tasks["total"] >= 4 and tasks["next_offset"] == 1

    asyncio.run(check())


def test_stdio_process_and_tool_errors():
    async def check():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "keep_context.cli", "serve", "--transport", "stdio", "--demo"],
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            await session.initialize()
            assert len((await session.list_tools()).tools) == 5
            found = await session.call_tool("search", {"query": "Cap Context"})
            assert found.structuredContent["results"][0]["id"] == "demo-cap-context"
            fetched = await session.call_tool("fetch", {"id": "demo-vlc"})
            assert "- [x] Build VLC" in fetched.structuredContent["text"]
            for name, args in [
                ("search", {"query": " "}),
                ("search", {"query": "a", "limit": 0}),
                ("fetch", {"id": "missing"}),
                ("unknown", {}),
            ]:
                assert (await session.call_tool(name, args)).isError

    asyncio.run(check())


def test_http_process_oauth_and_official_sdk(monkeypatch):
    # Use a real TCP server and official MCP client; no browser or UI automation.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    import test_auth

    monkeypatch.setattr(test_auth, "BASE", base)
    # Demo deliberately has a known password; no Google credentials are read.
    monkeypatch.setattr(test_auth, "PASSWORD", "demo-only-no-google-account")
    process = subprocess.Popen(
        [sys.executable, "-m", "keep_context.cli", "serve", "--demo", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "KEEP_PUBLIC_URL": base},
    )
    try:
        with httpx.Client(base_url=base, timeout=5) as http:
            for _ in range(100):
                try:
                    if http.get("/health").status_code == 200:
                        break
                except httpx.ConnectError:
                    pass
                time.sleep(0.1)
            else:
                pytest.fail("HTTP server did not start")
            info = register(http).json()
            token_response = exchange(http, info, approve(http, info), resource=base + "/mcp")
            assert token_response.status_code == 200, token_response.text
            token = token_response.json()["access_token"]

        async def check():
            async with httpx.AsyncClient(headers={"Authorization": "Bearer " + token}) as http:
                async with streamable_http_client(base + "/mcp", http_client=http) as (
                    read,
                    write,
                    _,
                ):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        tools = (await session.list_tools()).tools
                        assert len(tools) == 5
                        assert all(t.meta["securitySchemes"][0]["type"] == "oauth2" for t in tools)
                        for name, args in [
                            ("search", {"query": "Cap Context"}),
                            ("fetch", {"id": "demo-vlc"}),
                            ("list_recent_notes", {}),
                            ("list_labels", {}),
                            ("find_tasks", {}),
                        ]:
                            result = await session.call_tool(name, args)
                            assert not result.isError and result.structuredContent
                            assert "master_token" not in json.dumps(result.structuredContent)

        asyncio.run(check())
    finally:
        process.terminate()
        try:
            _, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            _, stderr = process.communicate(timeout=5)
        assert PASSWORD.encode() not in stderr
