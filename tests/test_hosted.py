import socket
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlparse

import pytest
import uvicorn
from cryptography.fernet import Fernet
from starlette.testclient import TestClient
from test_auth import BASE, begin, exchange, register

from keep_context.backend import DemoBackend
from keep_context.credentials import Credentials, SetupError
from keep_context.hosted import EXTENSION_ID, Pilot
from keep_context.hosted_store import HostedStore, exclusive_state

ORIGIN = "chrome-extension://" + EXTENSION_ID
KEY_A, KEY_B = "a" * 43, "b" * 43


def factory(credentials):
    backend = DemoBackend()
    backend._notes[0] = backend._notes[0].model_copy(
        update={
            "id": "same-id",
            "title": credentials.email,
            "body": "private " + credentials.email,
        }
    )
    return backend


@pytest.fixture
def pilot(tmp_path):
    key = Fernet.generate_key().decode()
    store = HostedStore(tmp_path / "pilot.enc", key, BASE + "/mcp")
    pilot = Pilot(
        BASE,
        store,
        factory=factory,
        exchange=lambda *args: "fake-google-master",
        open_enrollment=True,
    )
    with TestClient(pilot.app(8000), base_url=BASE) as http:
        yield http, pilot, key


def owner_headers(key):
    return {"Authorization": "Bearer " + key, "Origin": ORIGIN}


def connect(http, key, email):
    r = http.post(
        "/api/connect",
        headers={"Origin": ORIGIN},
        json={
            "device_key": key,
            "email": email,
            "cookie": "fake-only",
        },
    )
    assert r.status_code == 200
    for _ in range(200):
        state = http.get("/api/progress", headers=owner_headers(key)).json()
        if state["status"] != "connecting":
            assert state["status"] == "connected", state
            return
        time.sleep(0.01)
    pytest.fail("Enrollment did not finish")


def grant(http, info, key):
    location = begin(http, info).headers["location"]
    assert "No password needed" in http.get(location).text
    ticket = parse_qs(urlparse(location).query)["ticket"][0]
    r = http.post(
        "/api/approve", headers=owner_headers(key), json={"ticket": ticket, "action": "allow"}
    )
    assert r.status_code == 200
    values = parse_qs(urlparse(r.json()["redirect_url"]).query)
    assert values["state"] == ["a-client-state"]
    token = exchange(http, info, values["code"][0])
    assert token.status_code == 200
    return token.json(), ticket


def tool(http, token, name, args):
    return http.post(
        "/mcp",
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": args},
        },
    )


def test_direct_chatgpt_listing_configuration_is_safe(pilot):
    _, service, _ = pilot
    for listing in (
        "https://chatgpt.com/plugins/keep-context-example",
        "https://chatgpt.com/settings/plugins-settings/plugin_example",
    ):
        configured = Pilot(BASE, service.store, chatgpt_url=listing)
        with TestClient(configured.app(8000), base_url=BASE) as client:
            assert client.get("/api/config").json()["chatgpt_url"] == listing
    for invalid in (
        "https://chatgpt.com.evil.test/plugins/a",
        "https://user@chatgpt.com/plugins/a",
        "https://chatgpt.com/plugins/a?token=fake-only",
        "https://chatgpt.com/connector/oauth/a",
        "http://chatgpt.com/plugins/a",
        "javascript:alert(1)",
    ):
        with pytest.raises(SetupError):
            Pilot(BASE, service.store, chatgpt_url=invalid)


def test_ready_status_is_account_bound_and_uses_live_refresh_grants(pilot):
    http, service, _ = pilot
    connect(http, KEY_A, "alice@example.test")
    connect(http, KEY_B, "bob@example.test")

    def progress(key):
        return http.get("/api/progress", headers=owner_headers(key)).json()

    assert progress(KEY_A)["chatgpt_connected"] is False
    info = register(http).json()
    grant(http, info, KEY_A)
    assert progress(KEY_A)["chatgpt_connected"] is True
    assert progress(KEY_B)["chatgpt_connected"] is False
    for access in service.oauth.access.values():
        access.expires_at = time.time() - 1
    assert progress(KEY_A)["chatgpt_connected"] is True
    for refresh in service.oauth.refresh.values():
        refresh.expires_at = time.time() - 1
    assert progress(KEY_A)["chatgpt_connected"] is False
    grant(http, info, KEY_A)
    assert progress(KEY_A)["chatgpt_connected"] is True
    # Reconnecting the same email rotates ownership. The old completed job
    # must not report a connected account or leak its email to the old key.
    rotated = "c" * 43
    service.store.enroll(service.store.credentials(service.store.owner(KEY_B)), rotated)
    stale = progress(KEY_B)
    assert stale["status"] == "idle" and "email" not in stale
    assert progress(rotated)["chatgpt_connected"] is False
    assert http.post("/api/disconnect", headers=owner_headers(KEY_A), json={}).status_code == 200
    assert progress(KEY_A)["status"] == "idle"
    assert progress(rotated)["chatgpt_connected"] is False


def test_accounts_are_isolated_through_actual_mcp_routes(pilot):
    http, service, _ = pilot
    connect(http, KEY_A, "alice@example.test")
    connect(http, KEY_B, "bob@example.test")
    info = register(http).json()
    a, ticket = grant(http, info, KEY_A)
    b, _ = grant(http, info, KEY_B)
    for token, email, other in ((a, "alice", "bob"), (b, "bob", "alice")):
        for name, args in (
            ("search", {"query": email}),
            ("fetch", {"id": "same-id"}),
            ("list_recent_notes", {}),
            ("list_labels", {}),
            ("find_tasks", {}),
        ):
            result = tool(http, token["access_token"], name, args)
            assert result.status_code == 200 and not result.json()["result"].get("isError")
            assert other + "@example.test" not in result.text
            assert "fake-google-master" not in result.text
        assert (
            tool(http, token["access_token"], "fetch", {"id": "same-id"}).json()["result"][
                "structuredContent"
            ]["title"]
            == email + "@example.test"
        )
        assert (
            tool(http, token["access_token"], "search", {"query": other}).json()["result"][
                "structuredContent"
            ]["total"]
            == 0
        )
    assert http.post(
        "/api/approve", headers=owner_headers(KEY_A), json={"ticket": ticket, "action": "allow"}
    ).json() == {"status": "completed"}
    assert service.store.disk.path.read_bytes().find(b"fake-google-master") == -1


def test_restart_refresh_disconnect_and_encryption(pilot):
    http, service, key = pilot
    connect(http, KEY_A, "alice@example.test")
    info = register(http).json()
    tokens, _ = grant(http, info, KEY_A)
    store = HostedStore(service.store.disk.path, key, BASE + "/mcp")
    restarted = Pilot(BASE, store, factory=factory, open_enrollment=True)
    with TestClient(restarted.app(8000), base_url=BASE) as fresh:
        r = fresh.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "client_id": info["client_id"],
                "refresh_token": tokens["refresh_token"],
                "resource": BASE + "/mcp",
            },
        )
        assert r.status_code == 200
        refreshed = r.json()["access_token"]
        assert (
            tool(fresh, refreshed, "fetch", {"id": "same-id"}).json()["result"][
                "structuredContent"
            ]["title"]
            == "alice@example.test"
        )
        assert tool(fresh, tokens["access_token"], "fetch", {"id": "same-id"}).status_code == 401
        assert (
            fresh.post("/api/disconnect", headers=owner_headers(KEY_A), json={}).status_code == 200
        )
        assert tool(fresh, refreshed, "fetch", {"id": "same-id"}).status_code == 401
        assert fresh.get("/api/account", headers=owner_headers(KEY_A)).status_code == 401
    restored = HostedStore(service.store.disk.path, key, BASE + "/mcp")
    assert restored.data["accounts"] == {}
    with pytest.raises(SetupError):
        HostedStore(service.store.disk.path, Fernet.generate_key().decode(), BASE + "/mcp")
    with pytest.raises(SetupError):
        HostedStore(service.store.disk.path, key, "https://other.example/mcp")


def test_reconnect_revokes_old_device_and_mcp_access(pilot):
    http, _, _ = pilot
    connect(http, KEY_A, "alice@example.test")
    tokens, _ = grant(http, register(http).json(), KEY_A)
    connect(http, KEY_B, "alice@example.test")
    assert http.get("/api/account", headers=owner_headers(KEY_A)).status_code == 401
    assert tool(http, tokens["access_token"], "fetch", {"id": "same-id"}).status_code == 401
    assert http.get("/api/account", headers=owner_headers(KEY_B)).status_code == 200


def test_bad_origin_body_invitation_and_missing_owner_are_rejected(pilot):
    http, service, _ = pilot
    assert http.get("/api/config", headers={"Origin": "https://evil.example"}).status_code == 403
    assert (
        http.options("/api/connect", headers={"Origin": ORIGIN}).headers[
            "access-control-allow-origin"
        ]
        == ORIGIN
    )
    assert http.post("/api/connect", json=[]).status_code == 400
    assert http.post("/api/connect", content=b"x" * 65537).status_code == 413
    assert http.post("/api/approve", json={"ticket": "x", "action": "allow"}).status_code == 401
    assert http.get("/api/account", headers=owner_headers(KEY_A)).status_code == 401
    service.open_enrollment = False
    assert (
        http.post(
            "/api/connect",
            json={"device_key": KEY_A, "email": "alice@example.test", "cookie": "fake-only"},
        ).status_code
        == 400
    )
    assert not service.store.data["accounts"]


def test_failed_google_verification_is_safe_and_not_saved(pilot):
    http, service, _ = pilot

    def fail(*args):
        raise RuntimeError("upstream-secret-should-never-appear")

    service.exchange = fail
    assert (
        http.post(
            "/api/connect",
            json={"device_key": KEY_A, "email": "alice@example.test", "cookie": "fake-only"},
        ).status_code
        == 200
    )
    for _ in range(100):
        r = http.get("/api/progress", headers=owner_headers(KEY_A))
        if r.json()["status"] == "failed":
            break
        time.sleep(0.01)
    assert r.json()["status"] == "failed" and "upstream-secret" not in r.text
    assert service.store.data["accounts"] == {}


def test_expired_flow_cancel_and_recovered_response(pilot):
    http, service, _ = pilot
    connect(http, KEY_A, "alice@example.test")
    assert http.post("/api/connect", json={"device_key": KEY_A}).json()["status"] == "connected"
    info = register(http).json()
    location = begin(http, info).headers["location"]
    ticket = parse_qs(urlparse(location).query)["ticket"][0]
    service.oauth.pending[ticket].expires = time.time() - 1
    expired_page = http.get(location, follow_redirects=False)
    assert expired_page.status_code == 200 and 'id="flow-panel"' in expired_page.text
    assert http.get("/api/account", headers=owner_headers(KEY_A)).status_code == 200
    assert (
        http.post(
            "/api/approve", headers=owner_headers(KEY_A), json={"ticket": ticket, "action": "allow"}
        ).status_code
        == 400
    )
    ticket = parse_qs(urlparse(begin(http, info).headers["location"]).query)["ticket"][0]
    r = http.post(
        "/api/approve", headers=owner_headers(KEY_A), json={"ticket": ticket, "action": "cancel"}
    )
    assert "error=access_denied" in r.json()["redirect_url"] and not service.oauth.codes


def test_hosted_setup_has_time_and_expiry_preserves_google_connection(pilot):
    http, service, _ = pilot
    connect(http, KEY_A, "alice@example.test")
    location = begin(http, register(http).json()).headers["location"]
    ticket = parse_qs(urlparse(location).query)["ticket"][0]
    assert service.oauth.pending[ticket].expires > time.time() + 25 * 60
    service.oauth.pending[ticket].expires = time.time() - 1
    result = http.post("/api/pending", headers=owner_headers(KEY_A), json={"ticket": ticket})
    assert result.status_code == 200 and result.json()["status"] == "expired"
    assert "access_denied" in result.json()["retry_url"]
    assert http.get("/api/account", headers=owner_headers(KEY_A)).status_code == 200
    assert not service.oauth.codes


def test_lost_approval_response_can_finish_without_a_second_grant(pilot):
    http, service, _ = pilot
    connect(http, KEY_A, "alice@example.test")
    connect(http, KEY_B, "bob@example.test")
    info = register(http).json()
    location = begin(http, info).headers["location"]
    ticket = parse_qs(urlparse(location).query)["ticket"][0]
    payload = {"ticket": ticket, "action": "allow"}
    first = http.post("/api/approve", headers=owner_headers(KEY_A), json=payload).json()
    status = http.post("/api/pending", headers=owner_headers(KEY_A), json={"ticket": ticket})
    assert status.status_code == 200 and status.json()["status"] == "approved"
    assert "redirect_url" not in status.json()  # Polling exposes no authorization code.
    second = http.post("/api/approve", headers=owner_headers(KEY_A), json=payload)
    assert second.status_code == 200 and second.json() == first
    assert len(service.oauth.codes) == 1
    assert http.post("/api/approve", headers=owner_headers(KEY_B), json=payload).status_code == 400
    code = parse_qs(urlparse(first["redirect_url"]).query)["code"][0]
    assert exchange(http, info, code).status_code == 200
    status = http.post("/api/pending", headers=owner_headers(KEY_A), json={"ticket": ticket})
    assert status.json()["status"] == "completed"
    assert exchange(http, info, code).status_code == 400


def test_missing_chatgpt_link_is_recoverable_without_google_setup(pilot):
    http, _, _ = pilot
    connect(http, KEY_A, "alice@example.test")
    result = http.post("/api/pending", headers=owner_headers(KEY_A), json={"ticket": "x" * 43})
    assert result.status_code == 200 and result.json()["status"] == "unavailable"
    assert http.get("/api/account", headers=owner_headers(KEY_A)).status_code == 200


def test_approval_code_expiry_and_disconnect_do_not_reissue_access(pilot):
    http, service, _ = pilot
    connect(http, KEY_A, "alice@example.test")
    info = register(http).json()
    location = begin(http, info).headers["location"]
    ticket = parse_qs(urlparse(location).query)["ticket"][0]
    payload = {"ticket": ticket, "action": "allow"}
    response = http.post("/api/approve", headers=owner_headers(KEY_A), json=payload)
    code = parse_qs(urlparse(response.json()["redirect_url"]).query)["code"][0]
    service.oauth.codes[code].expires_at = time.time() - 1
    state = http.post("/api/pending", headers=owner_headers(KEY_A), json={"ticket": ticket}).json()
    assert state["status"] == "expired" and "redirect_url" not in state
    assert http.post("/api/approve", headers=owner_headers(KEY_A), json=payload).status_code == 400
    assert not service.oauth.codes
    response = http.post(
        "/api/approve", headers=owner_headers(KEY_A), json={"ticket": ticket, "action": "retry"}
    )
    assert "access_denied" in response.json()["redirect_url"]
    assert http.get("/api/account", headers=owner_headers(KEY_A)).status_code == 200
    assert http.post("/api/disconnect", headers=owner_headers(KEY_A), json={}).status_code == 200
    assert not service.oauth.decisions


def test_expired_flow_cannot_be_approved_and_returns_original_callback_state(pilot):
    http, service, _ = pilot
    connect(http, KEY_A, "alice@example.test")
    info = register(http).json()
    location = begin(http, info).headers["location"]
    ticket = parse_qs(urlparse(location).query)["ticket"][0]
    service.oauth.pending[ticket].expires = time.time() - 1
    assert (
        http.post(
            "/api/approve", headers=owner_headers(KEY_A), json={"ticket": ticket, "action": "allow"}
        ).status_code
        == 400
    )
    response = http.post(
        "/api/approve", headers=owner_headers(KEY_A), json={"ticket": ticket, "action": "retry"}
    )
    query = parse_qs(urlparse(response.json()["redirect_url"]).query)
    assert query["state"] == ["a-client-state"] and query["error"] == ["access_denied"]
    assert not service.oauth.codes


def test_store_capacity_and_device_key_never_persist_in_plaintext(tmp_path):
    key = Fernet.generate_key().decode()
    store = HostedStore(tmp_path / "s.enc", key, BASE + "/mcp", max_accounts=1)
    identity = store.enroll(Credentials("alice@example.test", "fake-only", "fake-id"), KEY_A)
    assert store.owner(KEY_A) == identity and store.owner("wrong") is None
    assert KEY_A not in str(store.data) and "fake-only" not in store.disk.path.read_text()
    with pytest.raises(SetupError):
        store.enroll(Credentials("bob@example.test", "fake-only", "fake-id"), KEY_B)


def test_duplicate_state_writer_fails_closed(tmp_path):
    path = tmp_path / "pilot.enc"
    with exclusive_state(path), pytest.raises(SetupError):
        with exclusive_state(path):
            pass
    with exclusive_state(path):
        pass


def test_extension_bridge_against_real_tcp_server(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    store = HostedStore(tmp_path / "s.enc", Fernet.generate_key().decode(), base + "/mcp")

    def fake_exchange(email, cookie, android_id):
        if cookie != "oauth2_4/fake-only":
            raise SetupError("Fake cookie rejected.")
        return "fake-master"

    pilot = Pilot(
        base, store, factory=lambda _: DemoBackend(), exchange=fake_exchange, open_enrollment=True
    )
    server = uvicorn.Server(
        uvicorn.Config(
            pilot.app(port), host="127.0.0.1", port=port, log_level="critical", access_log=False
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started
        result = subprocess.run(
            ["node", "extension/tests/wire-flow.mjs", base],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert "five MCP tools" in result.stdout
    finally:
        server.should_exit = True
        thread.join(5)
        assert not thread.is_alive()
