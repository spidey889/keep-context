import json
import time
from unittest.mock import Mock

import gkeepapi
import gpsoauth
import pytest
import requests

from keep_context.backend import (
    DeadlineAuthAdapter,
    KeepBackend,
    ReadOnlyKeepAPI,
    ReadOnlySession,
)
from keep_context.credentials import Credentials, SetupError


@pytest.fixture
def google(monkeypatch):
    source = gkeepapi.Keep()
    note = source.createNote("Cap Context", "VLC in the body\nTODO: interview")
    label = source.createLabel("Projects")
    note.labels.add(label)
    checklist = source.createList("VLC tasks", [("Pending", False), ("Finished", True)])
    checklist.add("Nested", False).indent(checklist.items[0])
    # dump() includes local dirty/cache markers in arrays too. save(clean=True)
    # produces the actual wire representation Google returns.
    nodes = [node for parent in source.all() for node in [parent, *parent.children]]
    snapshot = {
        "nodes": [node.save() for node in nodes],
        "labels": [label.save() for label in source.labels()],
    }
    payload = {
        "nodes": snapshot["nodes"],
        "userInfo": {"labels": snapshot["labels"]},
        "toVersion": "version-1",
        "truncated": False,
    }
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    auth = Mock(return_value={"Auth": "fake-google-access-secret"})
    monkeypatch.setattr(gpsoauth, "perform_oauth", auth)
    wire = Mock(return_value=response)
    monkeypatch.setattr(requests.Session, "request", wire)
    backend = KeepBackend(Credentials("fake@example.com", "fake-master-secret", "0123456789abcdef"))
    return backend, wire, auth


def test_real_gkeepapi_sync_conversion_and_no_uploads(google):
    backend, wire, auth = google
    result = backend.snapshot()
    assert len(result) == 2
    note = next(n for n in result if n.title == "Cap Context")
    assert note.body.startswith("VLC") and note.labels == ["Projects"]
    checklist = next(n for n in result if n.title == "VLC tasks")
    assert checklist.body == ""
    assert len(checklist.checklist) == 3
    assert any(item.parent_id for item in checklist.checklist)
    assert sum(item.checked for item in checklist.checklist) == 1
    assert backend.labels == ["Projects"]
    assert wire.call_count == 1 and auth.call_count == 1
    assert backend.snapshot() is result
    backend.snapshot(force=True)
    assert wire.call_count == 2
    for call in wire.call_args_list:
        assert not call.kwargs["json"]["nodes"]
        assert not call.kwargs["json"].get("userInfo")
        assert call.kwargs["timeout"] == (10, 30)


@pytest.mark.parametrize("payload", [{"nodes": [{"text": "edit"}]}, {"userInfo": {"labels": []}}])
def test_read_guard_blocks_mutations(payload):
    with pytest.raises(SetupError, match="mutation"):
        ReadOnlySession().request(
            "POST", "https://www.googleapis.com/notes/v1/changes", json=payload
        )


def test_read_guard_blocks_other_endpoints():
    with pytest.raises(SetupError, match="unexpected"):
        ReadOnlySession().request("DELETE", "https://www.googleapis.com/notes/v1/anything")


def test_auth_failure_redacted(google):
    backend, _, auth = google
    auth.side_effect = gkeepapi.exception.LoginException("TOKEN fake-master-secret")
    with pytest.raises(SetupError, match="authentication") as error:
        backend.snapshot()
    assert "fake-master-secret" not in str(error.value)


def test_network_failure_redacted_and_no_stale_fallback(google):
    backend, wire, _ = google
    backend.snapshot()
    wire.side_effect = requests.ConnectionError("secret token and note contents")
    with pytest.raises(SetupError, match="No stale results") as error:
        backend.snapshot(force=True)
    assert "secret" not in str(error.value)


def test_rate_limit_fails_promptly(google):
    backend, wire, _ = google
    wire.return_value.status_code = 429
    with pytest.raises(SetupError, match="rate limited"):
        backend.snapshot()
    assert wire.call_count == 1


def test_adapter_auth_timeout(monkeypatch):
    send = Mock(return_value=Mock())
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", send)
    DeadlineAuthAdapter().send(Mock(), timeout=None)
    assert send.call_args.kwargs["timeout"] == (10, 30)


def test_sync_deadline():
    api = ReadOnlyKeepAPI()
    api.deadline = time.monotonic() - 1
    with pytest.raises(SetupError, match="two minutes"):
        api.send()


def test_empty_checklist_remains_a_checklist():
    from keep_context.backend import convert
    from keep_context.notes import summary

    empty = gkeepapi.Keep().createList("Empty list")
    note = convert(empty)
    assert note.kind == "checklist" and summary(note)["type"] == "checklist"
    assert note.checklist == [] and note.body == ""
