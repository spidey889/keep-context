import pytest

from keep_context.notes import likely_tasks, page, search_notes, selected, summary


def search(notes, query, **kwargs):
    return search_notes(
        notes,
        query,
        kwargs.get("limit", 20),
        kwargs.get("offset", 0),
        kwargs.get("include_archived", True),
        kwargs.get("label"),
    )


def test_titles_bodies_checklists_unicode_and_archive(notes):
    result = search(notes, "vlc")
    assert {n["id"] for n in result["results"]} == {"vlc", "list", "archive", "unicode"}
    assert result["results"][0]["id"] in ("archive", "unicode")
    assert search(notes, "CAP context")["results"][0]["id"] == "cap"
    assert search(notes, "STRASSE")["results"][0]["id"] == "unicode"


def test_all_terms_and_label_filters(notes):
    assert search(notes, "VLC default")["total"] == 1
    assert search(notes, "VLC", label="projects")["total"] == 1
    assert search(notes, "VLC", include_archived=False)["total"] == 3
    assert search(notes, "absent")["results"] == []
    assert search(notes, "vlc", label="missing")["total"] == 0


def test_pagination_and_empty_query(notes):
    first = search(notes, "VLC", limit=2)
    second = search(notes, "VLC", offset=first["next_offset"], limit=2)
    assert len(first["results"]) == len(second["results"]) == 2
    assert second["next_offset"] is None
    assert page([], 5, 20) == {"results": [], "total": 0, "next_offset": None}
    with pytest.raises(ValueError, match="keyword"):
        search(notes, "   ")


def test_excerpt_finds_late_match(notes):
    note = notes[0].model_copy(update={"body": "x " * 500 + "VLC last line"})
    excerpt = summary(note, "VLC")["snippet"]
    assert "VLC" in excerpt and excerpt.startswith("…") and len(excerpt) < 360


def test_checklist_body_and_hierarchy(notes):
    note = next(n for n in notes if n.id == "list")
    assert "- [x] Buy bread" in note.text
    assert note.checklist[2].parent_id == "1"
    assert summary(note)["unchecked_items"] == 2


def test_tasks_distinguish_heuristics_and_checked_items(notes):
    result = likely_tasks(notes, False, None)
    texts = {t["text"] for t in result}
    assert {"VLC test device", "Nested task", "Ship release", "Remember to call Sam"} <= texts
    assert "Buy bread" not in texts
    assert not any("build" in text or "Completed:" in text or "hidden" in text for text in texts)
    assert any(t["reason"] == "task_language" and t["confidence"] == "likely" for t in result)
    assert any(t["reason"] == "unchecked_checklist" for t in result)
    assert any("compare" in t["text"] for t in likely_tasks(notes, True, None))
    assert all(t["labels"] == ["Projects"] for t in likely_tasks(notes, False, "Projects"))


def test_trashed_never_selected(notes):
    assert "trash" not in {n.id for n in selected(notes, True, None)}
