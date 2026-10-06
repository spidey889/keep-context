from datetime import UTC, datetime, timedelta

import pytest

from keep_context.notes import ChecklistItem, Note


@pytest.fixture
def notes():
    now = datetime(2026, 10, 6, 12, tzinfo=UTC)
    common = {"created": now, "updated": now, "url": "https://keep.google.com/"}
    return [
        Note(
            id="cap",
            title="Cap Context",
            body="Interview students\nTODO: show last transfer",
            labels=["Projects"],
            **common,
        ),
        Note(
            id="vlc",
            title="Video work",
            body="Investigate VLC and default app handling",
            labels=["Projects", "Work"],
            **{**common, "updated": now - timedelta(hours=1)},
        ),
        Note(
            id="list",
            title="Shopping",
            body="",
            checklist=[
                ChecklistItem(id="1", text="VLC test device", checked=False),
                ChecklistItem(id="2", text="Buy bread", checked=True),
                ChecklistItem(id="3", text="Nested task", checked=False, parent_id="1"),
            ],
            **common,
        ),
        Note(
            id="archive",
            title="VLC history",
            body="Need to compare releases",
            archived=True,
            labels=["Old"],
            **common,
        ),
        Note(
            id="trash",
            title="VLC deleted",
            body="TODO: should stay hidden",
            trashed=True,
            labels=["Deleted"],
            **common,
        ),
        Note(id="unicode", title="Straße ＶＬＣ", body="Über diese Notiz", **common),
        Note(
            id="markdown",
            title="Ideas",
            body="- [ ] Ship release\n- [x] Need to build\n"
            "Completed: follow up\nRemember to call Sam\nA normal sentence",
            **common,
        ),
    ]
