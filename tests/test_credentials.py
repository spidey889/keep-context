import json
from unittest.mock import Mock

import keyring
import pytest

from keep_context.credentials import (
    Credentials,
    SetupError,
    load_credentials,
    save_credentials,
    secure_keyring,
)
from keep_context.state import EncryptedState


def test_environment_credentials_and_safe_repr(monkeypatch):
    monkeypatch.setenv("KEEP_EMAIL", "fake@example.com")
    monkeypatch.setenv("KEEP_MASTER_TOKEN", "fake-master-secret")
    assert load_credentials().master_token == "fake-master-secret"
    assert "secret" not in repr(load_credentials())


def test_incomplete_environment_does_not_fallback(monkeypatch):
    monkeypatch.setenv("KEEP_EMAIL", "fake@example.com")
    monkeypatch.delenv("KEEP_MASTER_TOKEN", raising=False)
    with pytest.raises(SetupError, match="both"):
        load_credentials()


def test_plaintext_keyring_rejected(monkeypatch):
    monkeypatch.setattr(keyring, "get_keyring", lambda: Mock())
    with pytest.raises(SetupError, match="vault"):
        secure_keyring()


def test_native_keyring_save_load(monkeypatch):
    monkeypatch.delenv("KEEP_EMAIL", raising=False)
    monkeypatch.delenv("KEEP_MASTER_TOKEN", raising=False)
    native = type("Vault", (), {"__module__": "keyring.backends.Windows"})()
    monkeypatch.setattr(keyring, "get_keyring", lambda: native)
    store = {}
    monkeypatch.setattr(keyring, "set_password", lambda s, e, v: store.update({(s, e): v}))
    monkeypatch.setattr(keyring, "get_password", lambda s, e: store.get((s, e)))
    with pytest.raises(SetupError, match="not connected"):
        load_credentials()
    credentials = Credentials(
        "fake@example.com", "fake-master-secret", "0123456789abcdef", "fake-connection-password"
    )
    save_credentials(credentials)
    assert load_credentials() == credentials


def test_keyring_error_redacted(monkeypatch):
    native = type("Vault", (), {"__module__": "keyring.backends.Windows"})()
    monkeypatch.setattr(keyring, "get_keyring", lambda: native)
    monkeypatch.setattr(keyring, "set_password", Mock(side_effect=RuntimeError("secret")))
    with pytest.raises(SetupError, match="Cannot save") as error:
        save_credentials(Credentials("email", "token", "id"))
    assert "secret" not in str(error.value)


def test_encrypted_state_and_atomic_roundtrip(tmp_path):
    state = EncryptedState(tmp_path / "oauth.enc", "test-master-secret")
    value = {"access_token": "sensitive-access-token", "clients": {"abc": "secret"}}
    state.save(value)
    assert state.load() == value
    assert b"sensitive-access-token" not in state.path.read_bytes()
    assert not state.path.with_suffix(".enc.tmp").exists()
    with pytest.raises(SetupError, match="Cannot decrypt"):
        EncryptedState(state.path, "different-secret").load()
    assert "sensitive-access-token" not in json.dumps({"path": str(state.path)})
