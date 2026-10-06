import base64
import hashlib
import re
import time
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from keep_context.auth import OwnerOAuth
from keep_context.backend import DemoBackend
from keep_context.server import build_server, http_app
from keep_context.state import EncryptedState

PASSWORD = "a-test-connection-password-123"
BASE = "http://127.0.0.1:8000"
CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
VERIFIER = "v" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")
)


@pytest.fixture
def client():
    oauth = OwnerOAuth(BASE, PASSWORD)
    with TestClient(http_app(build_server(DemoBackend(), oauth), oauth), base_url=BASE) as http:
        yield http, oauth


def register(http, callback=CALLBACK):
    return http.post(
        "/register",
        json={
            "client_name": "Test client <script>",
            "redirect_uris": [callback],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )


def begin(http, info, resource=None):
    response = http.get(
        "/authorize",
        params={
            "client_id": info["client_id"],
            "redirect_uri": CALLBACK,
            "response_type": "code",
            "scope": "keep:read",
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
            "resource": resource or BASE + "/mcp",
            "state": "a-client-state",
        },
        follow_redirects=False,
    )
    return response


def approve(http, info):
    response = begin(http, info)
    assert response.status_code == 302
    location = response.headers["location"]
    form = http.get(location)
    assert "&lt;script&gt;" in form.text and "<script>" not in form.text
    csrf = re.search(r'name="csrf" value="([^"]+)"', form.text).group(1)
    approved = http.post(
        location, data={"password": PASSWORD, "csrf": csrf}, follow_redirects=False
    )
    assert approved.status_code == 303
    values = parse_qs(urlparse(approved.headers["location"]).query)
    assert values["state"] == ["a-client-state"]
    return values["code"][0]


def exchange(http, info, code, verifier=VERIFIER, resource=None):
    return http.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": info["client_id"],
            "redirect_uri": CALLBACK,
            "code_verifier": verifier,
            "resource": resource or BASE + "/mcp",
        },
    )


def test_discovery_and_denied_private_access(client):
    http, _ = client
    assert http.get("/health").json() == {"status": "ok", "service": "keep-context"}
    metadata = http.get("/.well-known/oauth-authorization-server").json()
    assert metadata["code_challenge_methods_supported"] == ["S256"]
    assert metadata["registration_endpoint"] == BASE + "/register"
    resource = http.get("/.well-known/oauth-protected-resource/mcp").json()
    assert resource["resource"] == BASE + "/mcp" and resource["scopes_supported"] == ["keep:read"]
    response = http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert (
        response.status_code == 401 and "resource_metadata" in response.headers["www-authenticate"]
    )
    assert "Cap Context" not in response.text
    assert http.get("/health", headers={"host": "evil.example"}).status_code == 400


@pytest.mark.parametrize(
    "callback",
    [
        "https://evil.example/callback",
        "http://chatgpt.com/cb",
        "https://chatgpt.com.evil.example/cb",
        "https://chatgpt.com/connector/oauth/abc?next=evil",
    ],
)
def test_redirect_allowlist(client, callback):
    http, _ = client
    assert register(http, callback).status_code == 400


def test_password_csrf_and_expired_flow(client):
    http, oauth = client
    info = register(http).json()
    location = begin(http, info).headers["location"]
    form = http.get(location)
    csrf = re.search(r'name="csrf" value="([^"]+)"', form.text).group(1)
    for data in ({"csrf": csrf, "password": "wrong"}, {"csrf": "wrong", "password": PASSWORD}):
        assert http.post(location, data=data).status_code == 403
    assert all("Google" not in str(code) for code in oauth.codes.values())
    ticket = parse_qs(urlparse(location).query)["ticket"][0]
    oauth.pending[ticket].expires = time.time() - 1
    assert http.get(location).status_code == 400


def test_password_rate_limit(client):
    http, _ = client
    info = register(http).json()
    location = begin(http, info).headers["location"]
    for _ in range(5):
        assert http.post(location, data={"password": "wrong"}).status_code == 403
    assert http.post(location, data={"password": "wrong"}).status_code == 429


def test_pkce_audience_expiry_rotation_and_replay(client):
    http, oauth = client
    info = register(http).json()
    bad = begin(http, info, "https://different.example/mcp")
    assert "invalid_request" in bad.headers["location"]
    code = approve(http, info)
    assert exchange(http, info, code, verifier="wrong").status_code == 400
    assert exchange(http, info, code, resource="https://evil.example").status_code == 400
    result = exchange(http, info, code)
    assert result.status_code == 200
    tokens = result.json()
    assert tokens["scope"] == "keep:read"
    assert exchange(http, info, code).status_code == 400
    access = oauth.access[tokens["access_token"]]
    assert access.resource == BASE + "/mcp"
    access.expires_at = int(time.time()) - 1
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    assert http.get("/mcp", headers=headers).status_code == 401
    data = {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": info["client_id"],
        "resource": BASE + "/mcp",
    }
    refreshed = http.post("/token", data=data)
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != tokens["refresh_token"]
    assert http.post("/token", data=data).status_code == 400
    token = refreshed.json()["access_token"]
    assert (
        http.post("/revoke", data={"client_id": info["client_id"], "token": token}).status_code
        == 200
    )
    assert token not in oauth.access


def test_cross_client_code_cannot_be_exchanged(client):
    http, _ = client
    first, second = register(http).json(), register(http).json()
    code = approve(http, first)
    assert exchange(http, second, code).status_code == 400
    assert exchange(http, first, code).status_code == 200


def test_body_limits_and_missing_resource(client):
    http, _ = client
    assert http.post("/connect", content="a" * 65537).status_code == 413
    assert http.post("/token", data={"grant_type": "refresh_token"}).status_code == 400


def test_persistent_oauth_is_encrypted_and_survives_restart(tmp_path):
    state = EncryptedState(tmp_path / "oauth.enc", "fake-google-master-secret")
    oauth = OwnerOAuth(BASE, PASSWORD, state=state)
    with TestClient(http_app(build_server(DemoBackend(), oauth), oauth), base_url=BASE) as http:
        info = register(http).json()
        tokens = exchange(http, info, approve(http, info)).json()
    assert tokens["access_token"].encode() not in state.path.read_bytes()
    replacement = OwnerOAuth(BASE, PASSWORD, state=state)
    assert tokens["access_token"] in replacement.access
    assert info["client_id"] in replacement.clients
    with pytest.raises(ValueError, match="URL changed"):
        OwnerOAuth("https://new.example", PASSWORD, state=state)
