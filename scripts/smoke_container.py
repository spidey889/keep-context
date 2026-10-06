"""CI-only container boot check. Generated test key never reaches source or output."""

import base64
import json
import os
import subprocess
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

environment = {**os.environ, "KEEP_HOSTED_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode()}
volume = "keep-context-ci-" + uuid.uuid4().hex
command = [
    "docker",
    "run",
    "--rm",
    "-d",
    "--name",
    "keep-context-ci",
    "-p",
    "8800:8800",
    "--mount",
    "type=volume,source=" + volume + ",target=/data",
    "-e",
    "KEEP_HOSTED_KEY",
    "-e",
    "KEEP_PUBLIC_URL=http://127.0.0.1:8800",
    "keep-context-pilot",
]


def start():
    subprocess.run(command, env=environment, check=True, capture_output=True)
    for _ in range(100):
        try:
            with urlopen("http://127.0.0.1:8800/health", timeout=2) as response:
                assert json.load(response)["status"] == "ok"
                break
        except (URLError, ConnectionError):
            time.sleep(0.2)
    else:
        raise RuntimeError("Container did not become healthy.")


def stop():
    subprocess.run(["docker", "stop", "keep-context-ci"], check=True, capture_output=True)


try:
    start()
    with urlopen("http://127.0.0.1:8800/api/config", timeout=2) as response:
        assert json.load(response)["invitation_required"] is True
    request = Request(
        "http://127.0.0.1:8800/mcp", data=b"{}", headers={"Content-Type": "application/json"}
    )
    try:
        urlopen(request, timeout=2)
        raise RuntimeError("Anonymous MCP request was accepted.")
    except HTTPError as error:
        assert error.code == 401
    # DCR forces an encrypted state write as the non-root container user. A second
    # container must restore the registered client from the same persistent volume.
    callback = "https://chatgpt.com/connector_platform_oauth_redirect"
    request = Request(
        "http://127.0.0.1:8800/register",
        data=json.dumps(
            {"redirect_uris": [callback], "token_endpoint_auth_method": "none"}
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=5) as response:
        client_id = json.load(response)["client_id"]
    stop()
    start()
    params = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": callback,
            "scope": "keep:read",
            "resource": "http://127.0.0.1:8800/mcp",
            "code_challenge": "a" * 43,
            "code_challenge_method": "S256",
        }
    )
    with urlopen("http://127.0.0.1:8800/authorize?" + params, timeout=5) as response:
        assert response.geturl().startswith("http://127.0.0.1:8800/connect?ticket=")
        assert response.headers["Cache-Control"] == "no-store"
        consent = response.read()
        # Verify the extension's consent contract rather than changeable page copy.
        for control in ("flow-fallback", "flow-panel", "flow-primary", "flow-cancel"):
            assert f'id="{control}"'.encode() in consent
    print("Container health, private MCP and encrypted volume persistence passed.")
finally:
    subprocess.run(["docker", "stop", "keep-context-ci"], capture_output=True)
    subprocess.run(["docker", "volume", "rm", volume], capture_output=True)
