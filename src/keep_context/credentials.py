"""Only explicit environment secrets or an OS credential vault; never plaintext fallback."""

import json
import os
from dataclasses import dataclass, field

import keyring

SERVICE = "keep-context"
ENTRY = "account"


class SetupError(Exception):
    """Safe, actionable message that must not include upstream error details."""


@dataclass
class Credentials:
    email: str = field(repr=False)
    master_token: str = field(repr=False)
    android_id: str = field(repr=False)
    connect_password: str = field(default="", repr=False)


def secure_keyring() -> None:
    backend = keyring.get_keyring()
    # keyrings.alt can silently write plaintext. Only known native vaults are accepted.
    allowed = (
        "keyring.backends.Windows",
        "keyring.backends.macOS",
        "keyring.backends.SecretService",
        "keyring.backends.kwallet",
    )
    if not type(backend).__module__.startswith(allowed):
        raise SetupError(
            "No supported OS credential vault. See docs/AUTHENTICATION.md for "
            "a native keyring or deployment environment-secret setup."
        )


def load_credentials() -> Credentials:
    email = os.environ.get("KEEP_EMAIL", "")
    token = os.environ.get("KEEP_MASTER_TOKEN", "")
    if email or token:
        if not email or not token:
            raise SetupError(
                "Set both KEEP_EMAIL and KEEP_MASTER_TOKEN, or remove both and "
                "run keep-context connect for OS-vault credentials."
            )
        return Credentials(
            email,
            token,
            os.environ.get("KEEP_ANDROID_ID", "0123456789abcdef"),
            os.environ.get("KEEP_CONNECT_PASSWORD", ""),
        )
    secure_keyring()
    try:
        raw = keyring.get_password(SERVICE, ENTRY)
        if not raw:
            raise SetupError("Google Keep is not connected. Run: uv run keep-context connect")
        return Credentials(**json.loads(raw))
    except SetupError:
        raise
    except Exception:
        raise SetupError(
            "Cannot read account credentials from the OS vault. Run connect again."
        ) from None


def save_credentials(credentials: Credentials) -> None:
    secure_keyring()
    try:
        keyring.set_password(SERVICE, ENTRY, json.dumps(vars(credentials)))
    except Exception:
        raise SetupError(
            "Cannot save credentials to the OS vault. Nothing was written to disk."
        ) from None


def disconnect() -> None:
    secure_keyring()
    try:
        keyring.delete_password(SERVICE, ENTRY)
    except keyring.errors.PasswordDeleteError:
        pass
