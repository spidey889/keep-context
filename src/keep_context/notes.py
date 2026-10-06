"""Pure read models and predictable, local keyword search; no Google mutations."""

import re
import unicodedata
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

PageSize = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0, le=100_000)]
Query = Annotated[str, Field(min_length=1, max_length=500)]


class ChecklistItem(BaseModel):
    id: str
    text: str
    checked: bool
    parent_id: str | None = None


class Note(BaseModel):
    id: str
    title: str
    body: str
    kind: Literal["note", "checklist"] = "note"
    url: str
    labels: list[str] = Field(default_factory=list)
    checklist: list[ChecklistItem] = Field(default_factory=list)
    created: datetime
    updated: datetime
    archived: bool = False
    trashed: bool = False
    pinned: bool = False

    @property
    def text(self) -> str:
        items = [f"- [{'x' if item.checked else ' '}] {item.text}" for item in self.checklist]
        return "\n".join(part for part in [self.body, *items] if part)


def normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def selected(notes: list[Note], include_archived: bool, label: str | None) -> list[Note]:
    return [
        note
        for note in notes
        if not note.trashed
        and (include_archived or not note.archived)
        and (label is None or normalize(label) in {normalize(x) for x in note.labels})
    ]


def summary(note: Note, query: str = "") -> dict:
    text = note.text
    # Center the excerpt on a body match so long notes do not hide why they matched.
    positions = [normalize(text).find(term) for term in normalize(query).split()]
    start = max(0, min((x for x in positions if x >= 0), default=0) - 80)
    return {
        "id": note.id,
        "title": note.title or "Untitled",
        "url": note.url,
        "snippet": ("…" if start else "")
        + text[start : start + 350]
        + ("…" if len(text) > start + 350 else ""),
        "labels": note.labels,
        "updated": note.updated.isoformat(),
        "archived": note.archived,
        "pinned": note.pinned,
        "type": "checklist" if note.checklist else note.kind,
        "unchecked_items": sum(not item.checked for item in note.checklist),
    }


def page(items: list[dict], limit: int, offset: int) -> dict:
    end = offset + limit
    return {
        "results": items[offset:end],
        "total": len(items),
        "next_offset": end if end < len(items) else None,
    }


def search_notes(
    notes: list[Note],
    query: str,
    limit: int,
    offset: int,
    include_archived: bool,
    label: str | None,
) -> dict:
    terms = normalize(query).split()
    if not terms:
        raise ValueError("Search needs at least one non-whitespace keyword.")
    matches = []
    for note in selected(notes, include_archived, label):
        title = normalize(note.title)
        body = normalize(note.text)
        haystack = title + "\n" + body
        if all(term in haystack for term in terms):
            score = sum(4 if term in title else 1 for term in terms)
            score += 5 if normalize(query) in title else 0
            matches.append((score, note))
    matches.sort(key=lambda item: (item[0], item[1].updated, item[1].id), reverse=True)
    return page([summary(note, query) for _, note in matches], limit, offset)


TASK_MARKER = re.compile(
    r"\b(?:todo|to\s+do|next\s+steps?|action\s+items?)\b|"
    r"\b(?:need\s+to|remember\s+to|must|follow\s+up|don't\s+forget\s+to)\b",
    re.IGNORECASE,
)
UNCHECKED = re.compile(r"^\s*[-*]?\s*\[ \]\s*(.+)$")
COMPLETED = re.compile(r"^\s*(?:[-*]?\s*\[[xX]\]|done\b|completed\b)", re.IGNORECASE)


def likely_tasks(notes: list[Note], include_archived: bool, label: str | None) -> list[dict]:
    tasks = []
    for note in sorted(
        selected(notes, include_archived, label), key=lambda n: (n.updated, n.id), reverse=True
    ):
        base = {
            "note_id": note.id,
            "note_title": note.title or "Untitled",
            "url": note.url,
            "labels": note.labels,
            "updated": note.updated.isoformat(),
        }
        for item in note.checklist:
            if not item.checked and item.text.strip():
                tasks.append(
                    {
                        **base,
                        "text": item.text,
                        "item_id": item.id,
                        "reason": "unchecked_checklist",
                        "confidence": "explicit",
                    }
                )
        title_is_task = bool(TASK_MARKER.search(note.title))
        for number, line in enumerate(note.body.splitlines(), 1):
            if not line.strip() or COMPLETED.match(line):
                continue
            checkbox = UNCHECKED.match(line)
            if checkbox or TASK_MARKER.search(line) or title_is_task:
                tasks.append(
                    {
                        **base,
                        "text": checkbox.group(1) if checkbox else line.strip(),
                        "line": number,
                        "reason": "unchecked_markdown" if checkbox else "task_language",
                        "confidence": "explicit" if checkbox else "likely",
                    }
                )
    return tasks
