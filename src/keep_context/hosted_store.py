"""Small encrypted pilot registry. Only one worker may own this state file."""

import base64
import copy
import hashlib
import os
import secrets
from contextlib import contextmanager
from pathlib import Path

from .credentials import Credentials, SetupError
from .state import EncryptedState


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@contextmanager
def exclusive_state(path: Path):
    """OS locks release on crash, unlike a PID file. Never run two writers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path.with_suffix(".lock"), "a+b")
    try:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            if not handle.read(1):
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise SetupError("Another hosted worker owns this state. Run exactly one worker.") from None
    try:
        yield
    finally:
        handle.close()


class HostedStore:
    def __init__(self, path: Path, key: str, resource: str, max_accounts: int = 50):
        try:
            if len(base64.urlsafe_b64decode(key)) != 32:
                raise ValueError
        except Exception:
            raise SetupError(
                "KEEP_HOSTED_KEY must be a Fernet key from the host's secret manager."
            ) from None
        self.disk = EncryptedState(path, "keep-context-hosted-v1\0" + key)
        self.data = self.disk.load() or {"resource": resource, "accounts": {}, "oauth": {}}
        if self.data.get("resource") != resource:
            raise SetupError(
                "Hosted public URL changed. Restore its stable URL; do not reset user data."
            )
        self.max_accounts = max_accounts

    def commit(self, data: dict) -> None:
        self.disk.save(data)
        self.data = data

    def load(self) -> dict:
        """The OAuth provider sees only its own part of the encrypted registry."""
        return copy.deepcopy(self.data["oauth"])

    def save(self, oauth: dict) -> None:
        self.commit({**self.data, "oauth": copy.deepcopy(oauth)})

    def owner(self, device_key: str) -> str | None:
        if not 40 <= len(device_key) <= 128:
            return None
        wanted = digest(device_key)
        for identity, account in self.data["accounts"].items():
            if secrets.compare_digest(account["device_hash"], wanted):
                return identity
        return None

    def credentials(self, identity: str) -> Credentials:
        account = self.data["accounts"].get(identity)
        if not account:
            raise SetupError("Keep is disconnected. Open the Keep Context extension to reconnect.")
        return Credentials(**account["credentials"])

    def enroll(self, credentials: Credentials, device_key: str) -> str:
        data = copy.deepcopy(self.data)
        # Reconnecting the same Google owner revokes the old browser/MCP grants.
        # A different account can never overwrite the current device's account.
        identity = next(
            (
                i
                for i, a in data["accounts"].items()
                if a["credentials"]["email"].casefold() == credentials.email.casefold()
            ),
            None,
        )
        if identity is None:
            if len(data["accounts"]) >= self.max_accounts:
                raise SetupError("This pilot is full. Contact the host for an invitation.")
            identity = secrets.token_urlsafe(18)
        data["accounts"][identity] = {
            "device_hash": digest(device_key),
            "credentials": vars(credentials),
        }
        oauth = data["oauth"]
        for name in ("access", "refresh"):
            oauth[name] = {
                k: v for k, v in oauth.get(name, {}).items() if v.get("subject") != identity
            }
        oauth["pairs"] = {
            a: r
            for a, r in oauth.get("pairs", {}).items()
            if a in oauth.get("access", {}) or r in oauth.get("refresh", {})
        }
        self.commit(data)
        return identity

    def delete(self, identity: str) -> None:
        data = copy.deepcopy(self.data)
        data["accounts"].pop(identity, None)
        self.commit(data)
