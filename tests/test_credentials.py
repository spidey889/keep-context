import json
from unittest.mock import Mock

import keyring
import pytest

from keep_context.credentials import (
    Credentials,
    SetupError,
    clear_pending_credentials,
    disconnect,
    load_credentials,
    load_pending_credentials,
    save_credentials,
    save_pending_credentials,
    secure_keyring,
)
from keep_context.state import EncryptedState


@pytest.fixture
def native_vault(monkeypatch):
    monkeypatch.delenv("KEEP_EMAIL", raising=False)
    monkeypatch.delenv("KEEP_MASTER_TOKEN", raising=False)
    native = type("Vault", (), {"__module__": "keyring.backends.Windows"})()
    monkeypatch.setattr(keyring, "get_keyring", lambda: native)
    store = {}
    monkeypatch.setattr(keyring, "set_password", lambda s, e, v: store.update({(s, e): v}))
    monkeypatch.setattr(keyring, "get_password", lambda s, e: store.get((s, e)))
    monkeypatch.setattr(keyring, "delete_password", lambda s, e: store.pop((s, e), None))
    return store


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


def test_setup_progress_is_separate_and_disconnect_removes_both(native_vault):
    existing = Credentials("old@example.com", "old-token", "old-id", "old-connection-password")
    pending = Credentials("new@example.com", "new-token", "new-id", "unused-secret-password")
    save_credentials(existing)
    assert load_pending_credentials() is None
    save_pending_credentials(pending)
    assert load_credentials() == existing
    restored = load_pending_credentials()
    assert restored.master_token == pending.master_token and restored.connect_password == ""
    clear_pending_credentials()
    assert load_pending_credentials() is None and load_credentials() == existing
    save_pending_credentials(pending)
    disconnect()
    assert not native_vault


def test_progress_cannot_be_used_as_server_credentials(native_vault):
    save_pending_credentials(Credentials("fake@example.com", "fake-token", "id"))
    with pytest.raises(SetupError, match="not connected"):
        load_credentials()


@pytest.mark.parametrize("operation", ["load", "save", "delete"])
def test_setup_progress_vault_errors_are_redacted(monkeypatch, native_vault, operation):
    broken = Mock(side_effect=RuntimeError("sensitive-upstream-secret"))
    if operation == "load":
        monkeypatch.setattr(keyring, "get_password", broken)
        action = load_pending_credentials
    elif operation == "save":
        monkeypatch.setattr(keyring, "set_password", broken)

        def action():
            save_pending_credentials(Credentials("fake", "fake-token", "id"))

    else:
        monkeypatch.setattr(keyring, "delete_password", broken)
        action = clear_pending_credentials
    with pytest.raises(SetupError) as error:
        action()
    assert "sensitive-upstream-secret" not in str(error.value)


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
