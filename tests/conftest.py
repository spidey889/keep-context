from datetime import UTC, datetime, timedelta

import pytest

from keep_context.notes import ChecklistItem, Note


@pytest.fixture
def notes():
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    common = {"created": now, "updated": now, "url": "https://keep.google.com/"}
    return [
        Note(
            id="garden",
            title="Garden plan",
            body="Choose vegetables\nTODO: order seeds",
            labels=["Projects"],
            **common,
        ),
        Note(
            id="trip",
            title="Travel plans",
            body="Plan a trip and hotel booking",
            labels=["Projects", "Work"],
            **{**common, "updated": now - timedelta(hours=1)},
        ),
        Note(
            id="list",
            title="Shopping",
            body="",
            checklist=[
                ChecklistItem(id="1", text="Trip packing list", checked=False),
                ChecklistItem(id="2", text="Buy bread", checked=True),
                ChecklistItem(id="3", text="Nested task", checked=False, parent_id="1"),
            ],
            **common,
        ),
        Note(
            id="archive",
            title="Trip history",
            body="Need to compare routes",
            archived=True,
            labels=["Old"],
            **common,
        ),
        Note(
            id="trash",
            title="Trip deleted",
            body="TODO: should stay hidden",
            trashed=True,
            labels=["Deleted"],
            **common,
        ),
        Note(id="unicode", title="Straße ＴＲＩＰ", body="Über diese Notiz", **common),
        Note(
            id="markdown",
            title="Ideas",
            body="- [ ] Ship release\n- [x] Need to build\n"
            "Completed: follow up\nRemember to call Sam\nA normal sentence",
            **common,
        ),
    ]
