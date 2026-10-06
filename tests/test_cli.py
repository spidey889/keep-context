from unittest.mock import Mock

import pytest

from keep_context import cli
from keep_context.credentials import SetupError


def test_hidden_input_rejects_noninteractive(monkeypatch):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    with pytest.raises(SetupError, match="interactive"):
        cli.hidden("Secret: ")


def test_connect_saves_only_after_verification(monkeypatch, capsys):
    values = iter(["fake-oauth-cookie", "a-test-connection-password", "a-test-connection-password"])
    monkeypatch.setattr("builtins.input", lambda _: "fake@example.com")
    monkeypatch.setattr(cli, "hidden", lambda _: next(values))
    monkeypatch.setattr(
        cli.gpsoauth, "exchange_token", lambda *args: {"Token": "fake-google-master"}
    )
    backend = Mock()
    backend.snapshot.return_value = []
    monkeypatch.setattr(cli, "KeepBackend", lambda credentials: backend)
    saved = Mock()
    monkeypatch.setattr(cli, "save_credentials", saved)
    cli.connect()
    assert saved.call_args.args[0].master_token == "fake-google-master"
    output = capsys.readouterr().out
    assert "fake-google-master" not in output and "fake-oauth-cookie" not in output
    assert "a-test-connection-password" not in output


def test_failed_exchange_never_saves_or_prints_upstream(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "fake@example.com")
    monkeypatch.setattr(cli, "hidden", lambda _: "fake-oauth-cookie")
    monkeypatch.setattr(cli.gpsoauth, "exchange_token", lambda *args: {"Error": "secret"})
    save = Mock()
    monkeypatch.setattr(cli, "save_credentials", save)
    with pytest.raises(SetupError, match="rejected") as error:
        cli.connect()
    assert not save.called and "secret" not in str(error.value)


@pytest.mark.parametrize(
    "value",
    [
        "http://example.com",
        "https://user:secret@example.com",
        "https://example.com/mcp",
        "https://example.com/?token=secret",
    ],
)
def test_bad_public_url(value):
    with pytest.raises(SetupError):
        cli.public_url(value)


def test_loopback_and_https_public_url():
    assert cli.public_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"
    assert cli.public_url("https://keep.example.com/") == "https://keep.example.com"
