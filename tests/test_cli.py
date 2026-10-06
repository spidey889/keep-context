from dataclasses import replace
from unittest.mock import Mock

import pytest

from keep_context import cli
from keep_context.credentials import SetupError


@pytest.fixture(autouse=True)
def isolated_setup_vault(monkeypatch):
    # CLI tests must never read or overwrite the user's actual account/checkpoint.
    monkeypatch.setattr(cli, "load_pending_credentials", Mock(return_value=None))
    monkeypatch.setattr(cli, "save_pending_credentials", Mock())
    monkeypatch.setattr(cli, "clear_pending_credentials", Mock())


def test_hidden_input_rejects_noninteractive(monkeypatch):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False)
    with pytest.raises(SetupError, match="interactive"):
        cli.hidden("Secret: ")


def test_connect_saves_only_after_verification(monkeypatch, capsys):
    values = iter(
        ["oauth2_4/fake-oauth-cookie", "a-test-connection-password", "a-test-connection-password"]
    )
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
    timeline = Mock()
    timeline.attach_mock(backend.snapshot, "verify")
    timeline.attach_mock(cli.save_pending_credentials, "checkpoint")
    timeline.attach_mock(saved, "save")
    timeline.attach_mock(cli.clear_pending_credentials, "clear")
    cli.connect()
    assert [call[0] for call in timeline.method_calls] == ["verify", "checkpoint", "save", "clear"]
    assert saved.call_args.args[0].master_token == "fake-google-master"
    output = capsys.readouterr().out
    assert "fake-google-master" not in output and "fake-oauth-cookie" not in output
    assert "a-test-connection-password" not in output


def test_failed_exchange_never_saves_or_prints_upstream(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "fake@example.com")
    monkeypatch.setattr(cli, "hidden", lambda _: "oauth2_4/fake-oauth-cookie")
    monkeypatch.setattr(cli.gpsoauth, "exchange_token", lambda *args: {"Error": "secret"})
    save = Mock()
    monkeypatch.setattr(cli, "save_credentials", save)
    with pytest.raises(SetupError, match="rejected") as error:
        cli.connect()
    assert not save.called and "secret" not in str(error.value)


@pytest.mark.parametrize("code", ["BadAuthentication", "NeedsBrowser", "MissingDroidguard"])
def test_exchange_shows_only_known_code_and_never_saves(monkeypatch, capsys, code):
    monkeypatch.setattr("builtins.input", lambda _: "fake@example.com")
    monkeypatch.setattr(cli, "hidden", lambda _: "oauth2_4/fake-oauth-cookie")
    monkeypatch.setattr(
        cli.gpsoauth,
        "exchange_token",
        lambda *args: {"Error": code, "Url": "https://example.com/?secret=fake-secret"},
    )
    save = Mock()
    monkeypatch.setattr(cli, "save_credentials", save)
    with pytest.raises(SetupError, match=code) as error:
        cli.connect()
    assert "No credentials were saved" in str(error.value)
    assert "fake-secret" not in str(error.value) + capsys.readouterr().out
    assert not save.called


@pytest.mark.parametrize(
    "cookie",
    ["", "oauth_token", "oauth_token=oauth2_4/fake", "oauth2_4/fake other", '"oauth2_4/fake"'],
)
def test_invalid_cookie_fails_before_network_and_vault(monkeypatch, cookie):
    monkeypatch.setattr("builtins.input", lambda _: "fake@example.com")
    monkeypatch.setattr(cli, "hidden", lambda _: cookie)
    exchange = Mock()
    save = Mock()
    monkeypatch.setattr(cli.gpsoauth, "exchange_token", exchange)
    monkeypatch.setattr(cli, "save_credentials", save)
    with pytest.raises(SetupError, match="Copy only"):
        cli.connect()
    assert not exchange.called and not save.called


def test_exchange_exception_does_not_reveal_cookie_or_error(monkeypatch):
    exchange = Mock(side_effect=RuntimeError("upstream-secret oauth2_4/fake-oauth-cookie"))
    monkeypatch.setattr(cli.gpsoauth, "exchange_token", exchange)
    with pytest.raises(SetupError, match="exchange failed") as error:
        cli.exchange_google_token("fake@example.com", "oauth2_4/fake-oauth-cookie", "fake-device")
    assert "upstream-secret" not in str(error.value)
    assert "fake-oauth-cookie" not in str(error.value)


@pytest.mark.parametrize(
    "attempts",
    [
        ["short", "a-test-connection-password", "a-test-connection-password"],
        [
            "a-test-connection-password",
            "wrong",
            "a-new-connection-password",
            "a-new-connection-password",
        ],
    ],
)
def test_bad_password_retries_without_repeating_google(monkeypatch, capsys, attempts):
    values = iter(["oauth2_4/fake-oauth-cookie", *attempts])
    monkeypatch.setattr("builtins.input", lambda _: "fake@example.com")
    monkeypatch.setattr(cli, "hidden", lambda _: next(values))
    exchange = Mock(return_value={"Token": "fake-google-master"})
    backend = Mock()
    backend.snapshot.return_value = []
    saved = Mock()
    monkeypatch.setattr(cli.gpsoauth, "exchange_token", exchange)
    monkeypatch.setattr(cli, "KeepBackend", lambda _: backend)
    monkeypatch.setattr(cli, "save_credentials", saved)
    cli.connect()
    assert exchange.call_count == backend.snapshot.call_count == saved.call_count == 1
    assert saved.call_args.args[0].connect_password == attempts[-1]
    output = capsys.readouterr().out
    assert "Try again" in output
    assert "fake-google-master" not in output and attempts[-1] not in output


def test_interrupted_setup_resumes_without_email_or_cookie(monkeypatch, capsys):
    pending = {}
    values = iter(
        [
            "oauth2_4/fake-oauth-cookie",
            KeyboardInterrupt(),
            "a-test-connection-password",
            "a-test-connection-password",
        ]
    )

    def hidden(_):
        value = next(values)
        if isinstance(value, BaseException):
            raise value
        return value

    email_input = Mock(return_value="fake@example.com")
    monkeypatch.setattr("builtins.input", email_input)
    monkeypatch.setattr(cli, "hidden", hidden)
    monkeypatch.setattr(cli, "load_pending_credentials", lambda: pending.get("credentials"))
    monkeypatch.setattr(
        cli,
        "save_pending_credentials",
        lambda credentials: pending.update(credentials=replace(credentials, connect_password="")),
    )
    monkeypatch.setattr(cli, "clear_pending_credentials", lambda: pending.clear())
    exchange = Mock(return_value={"Token": "fake-google-master"})
    backend = Mock()
    backend.snapshot.return_value = []
    saved = Mock()
    monkeypatch.setattr(cli.gpsoauth, "exchange_token", exchange)
    monkeypatch.setattr(cli, "KeepBackend", lambda _: backend)
    monkeypatch.setattr(cli, "save_credentials", saved)
    cli.connect()
    assert pending["credentials"].master_token == "fake-google-master"
    assert not saved.called
    cli.connect()
    assert email_input.call_count == exchange.call_count == saved.call_count == 1
    assert backend.snapshot.call_count == 2
    assert not pending
    output = capsys.readouterr().out
    assert "Setup paused" in output and "Resuming saved Google setup" in output
    assert "fake-google-master" not in output and "a-test-connection-password" not in output


def test_failed_keep_verification_never_saves_progress(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "fake@example.com")
    monkeypatch.setattr(cli, "hidden", lambda _: "oauth2_4/fake-oauth-cookie")
    monkeypatch.setattr(cli.gpsoauth, "exchange_token", Mock(return_value={"Token": "fake-master"}))
    backend = Mock()
    backend.snapshot.side_effect = SetupError("Keep read failed")
    monkeypatch.setattr(cli, "KeepBackend", lambda _: backend)
    saved = Mock()
    monkeypatch.setattr(cli, "save_credentials", saved)
    with pytest.raises(SetupError, match="Keep read failed"):
        cli.connect()
    assert not saved.called and not cli.save_pending_credentials.called


def test_failed_final_save_preserves_checkpoint(monkeypatch):
    monkeypatch.setattr(
        cli, "load_pending_credentials", lambda: cli.Credentials("fake", "fake", "id")
    )
    monkeypatch.setattr(cli, "hidden", lambda _: "a-test-connection-password")
    backend = Mock()
    backend.snapshot.return_value = []
    monkeypatch.setattr(cli, "KeepBackend", lambda _: backend)
    monkeypatch.setattr(cli, "save_credentials", Mock(side_effect=SetupError("Vault failed")))
    with pytest.raises(SetupError, match="Vault failed"):
        cli.connect()
    assert cli.save_pending_credentials.called and not cli.clear_pending_credentials.called


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
