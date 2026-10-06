import io
from unittest.mock import Mock

import pytest

from keep_context import tunnel
from keep_context.credentials import SetupError


def test_missing_tunnel_binary(monkeypatch):
    monkeypatch.setattr(tunnel.shutil, "which", lambda _: None)
    with pytest.raises(SetupError, match="Install cloudflared"), tunnel.open_tunnel(8000):
        pass


def test_tunnel_cleanup_on_exception(monkeypatch):
    process = Mock()
    process.poll.return_value = None
    process.stdout = io.StringIO(
        "Tunnel available at https://demo-test.trycloudflare.com\nRegistered tunnel connection\n"
    )
    monkeypatch.setattr(tunnel.shutil, "which", lambda _: "fake-cloudflared")
    monkeypatch.setattr(tunnel.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(RuntimeError, match="intentional"):
        with tunnel.open_tunnel(8000) as url:
            assert url == "https://demo-test.trycloudflare.com"
            raise RuntimeError("intentional")
    process.terminate.assert_called_once()
    assert process.stdout.closed
