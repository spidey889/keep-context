"""Encrypted, atomic OAuth state; no note cache or Google credentials on disk."""

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

from .credentials import SetupError


class EncryptedState:
    def __init__(self, path: Path, master_token: str):
        self.path = path
        # Domain-separated derivation from an existing high-entropy vault secret avoids
        # needing another OS-vault entry. Rotating the Google token invalidates old state.
        key = hashlib.sha256(b"keep-context-oauth-v1\0" + master_token.encode()).digest()
        self.cipher = Fernet(base64.urlsafe_b64encode(key))

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.cipher.decrypt(self.path.read_bytes()))
        except Exception:
            raise SetupError(
                "Cannot decrypt OAuth state. If you changed Google credentials, "
                "start serve with --reset-access and reconnect ChatGPT."
            ) from None

    def save(self, data: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            payload = self.cipher.encrypt(json.dumps(data).encode())
            with open(temporary, "wb") as handle:
                os.chmod(temporary, 0o600)
                handle.write(payload)
            os.replace(temporary, self.path)
        except Exception:
            raise SetupError(
                "Cannot save encrypted OAuth state. Check state directory permissions."
            ) from None
