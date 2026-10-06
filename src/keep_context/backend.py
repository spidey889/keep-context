"""A serialized, bounded, read-only adapter around the maintained gkeepapi client."""

import logging
import threading
import time
from datetime import UTC, datetime
from urllib.parse import quote

import gkeepapi
import gpsoauth
import requests

from .credentials import Credentials, SetupError
from .notes import ChecklistItem, Note


def quiet_upstream() -> None:
    # Upstream parsing exceptions/debug logs may include whole notes and auth responses.
    for name in ("gkeepapi", "gpsoauth", "urllib3", "httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


class TimeoutSession(requests.Session):
    def request(self, method, url, **kwargs):
        kwargs.setdefault("timeout", (10, 30))
        return super().request(method, url, **kwargs)


class ReadOnlySession(TimeoutSession):
    def request(self, method, url, **kwargs):
        # Google's read sync uses POST. An empty mutation payload is essential: even
        # an accidental future gkeepapi model edit must never be uploaded by sync().
        payload = kwargs.get("json") or {}
        if method.upper() != "POST" or not url.endswith("/changes"):
            raise SetupError("Read-only guard rejected an unexpected Google API request.")
        if payload.get("nodes") or payload.get("userInfo"):
            raise SetupError("Read-only guard rejected a Google Keep mutation.")
        return super().request(method, url, **kwargs)


class DeadlineAuthAdapter(gpsoauth.AuthHTTPAdapter):
    def send(self, request, **kwargs):
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = (10, 30)
        return super().send(request, **kwargs)


# gpsoauth 2.0 exposes no session/timeout parameter. Preserve its TLS adapter and
# request generation, adding a deadline only at its adapter boundary.
gpsoauth.AuthHTTPAdapter = DeadlineAuthAdapter


class ReadOnlyKeepAPI(gkeepapi.KeepAPI):
    def __init__(self):
        super().__init__()
        self._session.close()
        self._session = ReadOnlySession()
        self.deadline = 0.0

    def send(self, **kwargs):
        # Upstream retries 429 forever. A private MCP call must instead fail cleanly.
        for attempt in range(2):
            if time.monotonic() > self.deadline:
                raise SetupError("Google Keep sync exceeded two minutes. Retry later.")
            response = self._send(**kwargs)
            if response.status_code == 429:
                raise SetupError("Google Keep rate limited this connection. Retry later.")
            if response.status_code == 401:
                if attempt == 0:
                    self._auth.refresh()
                    continue
                raise gkeepapi.exception.LoginException("Authentication rejected")
            response.raise_for_status()
            data = response.json()
            if "error" in data:
                if data["error"].get("code") == 401:
                    if attempt == 0:
                        self._auth.refresh()
                        continue
                    raise gkeepapi.exception.LoginException("Authentication rejected")
                raise SetupError("Google Keep rejected the sync. Retry later or reconnect.")
            return data
        raise gkeepapi.exception.LoginException("Authentication rejected")


def timestamp(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def convert(node) -> Note:
    checklist = []
    is_list = isinstance(node, gkeepapi.node.List)
    if is_list:
        for item in node.items:
            parent_id = item.parent_item.id if item.parent_item else None
            checklist.append(
                ChecklistItem(id=item.id, text=item.text, checked=item.checked, parent_id=parent_id)
            )
    return Note(
        id=node.id,
        title=node.title,
        body="" if is_list else node.text,
        kind="checklist" if is_list else "note",
        url="https://keep.google.com/#NOTE/" + quote(node.server_id or node.id, safe=""),
        labels=sorted(label.name for label in node.labels.all()),
        checklist=checklist,
        created=timestamp(node.timestamps.created),
        updated=timestamp(node.timestamps.updated),
        archived=node.archived,
        trashed=node.trashed,
        pinned=node.pinned,
    )


class KeepBackend:
    def __init__(self, credentials: Credentials, ttl: int = 60):
        self.credentials = credentials
        self.ttl = ttl
        self._lock = threading.Lock()
        self._keep = None
        self._notes: list[Note] = []
        self._synced = 0.0
        self.updated_at: str | None = None
        self.labels: list[str] = []

    def snapshot(self, force: bool = False) -> list[Note]:
        with self._lock:
            if not force and self._keep is not None and time.monotonic() - self._synced < self.ttl:
                return self._notes
            quiet_upstream()
            try:
                if self._keep is None:
                    keep = gkeepapi.Keep()
                    keep._keep_api = ReadOnlyKeepAPI()
                    keep._keep_api.deadline = time.monotonic() + 120
                    auth = gkeepapi.APIAuth(keep.OAUTH_SCOPES)
                    auth.load(
                        self.credentials.email,
                        self.credentials.master_token,
                        self.credentials.android_id,
                    )
                    keep.load(auth)
                else:
                    keep = self._keep
                    keep._keep_api.deadline = time.monotonic() + 120
                    keep.sync()
                notes = [convert(node) for node in keep.all()]
                labels = [label.name for label in keep.labels()]
            except (
                gkeepapi.exception.LoginException,
                gkeepapi.exception.BrowserLoginRequiredException,
            ):
                self._keep = None
                raise SetupError(
                    "Google authentication expired or was rejected. Run connect again."
                ) from None
            except SetupError:
                self._keep = None
                raise
            except Exception:
                # Never forward Google's responses, note parse errors, or token-bearing URLs.
                self._keep = None
                raise SetupError(
                    "Google Keep could not sync. Check your network and account access, "
                    "then retry. No stale results were returned."
                ) from None
            self._keep = keep
            self._notes = notes
            self.labels = labels
            self._synced = time.monotonic()
            self.updated_at = datetime.now(UTC).isoformat()
            return notes


class DemoBackend:
    def __init__(self):
        now = datetime(2026, 10, 6, 12, tzinfo=UTC)
        self.updated_at = now.isoformat()
        self.labels = ["Projects", "Ideas"]
        self._notes = [
            Note(
                id="demo-garden",
                title="Garden plan",
                body="Choose vegetables for spring.\nTODO: order seeds.",
                labels=["Projects", "Ideas"],
                url="https://keep.google.com/",
                created=now,
                updated=now,
            ),
            Note(
                id="demo-trip",
                title="Weekend trip",
                body="",
                labels=["Projects"],
                url="https://keep.google.com/",
                created=now,
                updated=now,
                checklist=[
                    ChecklistItem(id="trip-1", text="Book a place to stay", checked=False),
                    ChecklistItem(id="trip-2", text="Pack a bag", checked=True),
                ],
            ),
        ]

    def snapshot(self, force: bool = False) -> list[Note]:
        return self._notes
