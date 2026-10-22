"""Structured assessment state and its persistence (SQLite, one JSON row per assessment)."""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .config import settings

Status = Literal["present", "absent", "unsure"]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class SymptomEntry(BaseModel):
    id: str
    status: Status
    user_words: list[str] = Field(default_factory=list)
    source: Literal["text", "answer", "edit", "llm"] = "text"
    intensity: str | None = None
    updated_turn: int = 0


class Attributes(BaseModel):
    age_group: str | None = None
    duration_days: float | None = None
    recurring: bool = False
    onset: str | None = None
    severity: int | None = None
    severity_hint: str | None = None
    progression: str | None = None
    risk_pregnant: bool = False
    risk_longterm: bool = False
    risk_immune: bool = False
    trigger_food_med: bool = False


class FlagRecord(BaseModel):
    id: str
    level: str
    matched: str
    source: Literal["text", "answer", "state"] = "text"
    turn: int = 0
    dismissed: bool = False


class Message(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    turn: int
    kind: str = "text"


class AssessmentState(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    language: Literal["en", "hi"] = "hi"
    created_at: str = Field(default_factory=now)
    updated_at: str = Field(default_factory=now)
    turn: int = 0
    symptoms: dict[str, SymptomEntry] = Field(default_factory=dict)
    attributes: Attributes = Field(default_factory=Attributes)
    red_flags: list[FlagRecord] = Field(default_factory=list)
    dismissed_flags: list[str] = Field(default_factory=list)
    asked: list[str] = Field(default_factory=list)
    answers: dict[str, Any] = Field(default_factory=dict)
    pending_question: str | None = None
    clarifications: list[str] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    assessment_requested: bool = False
    unrecognised: list[str] = Field(default_factory=list)
    version: int = 0

    def set_symptom(self, sid: str, status: str, source: str, words: str | None, turn: int,
                    intensity: str | None = None) -> None:
        e = self.symptoms.get(sid)
        if e is None:
            e = SymptomEntry(id=sid, status=status, source=source, updated_turn=turn)
            self.symptoms[sid] = e
        e.status = status
        e.source = source
        e.updated_turn = turn
        if intensity:
            e.intensity = intensity
        if words and words not in e.user_words:
            e.user_words.append(words)

    def status_map(self) -> dict[str, str]:
        return {s: e.status for s, e in self.symptoms.items()}

    def present(self) -> set[str]:
        return {s for s, e in self.symptoms.items() if e.status == "present"}

    def active_flags(self) -> list[FlagRecord]:
        return [f for f in self.red_flags if not f.dismissed and f.id not in self.dismissed_flags]

    def user_texts(self) -> list[str]:
        return [m.text for m in self.messages if m.role == "user" and m.kind == "text"]


class StateStore:
    """Thread-safe SQLite store. Falls back to memory if the DB path is unusable."""

    def __init__(self, path: str | None = None):
        self.path = path or settings.db_path
        self._lock = threading.Lock()
        self._memory: dict[str, str] | None = None
        try:
            if self.path != ":memory:":
                Path(self.path).parent.mkdir(parents=True, exist_ok=True)
                with self._conn() as c:
                    c.execute("CREATE TABLE IF NOT EXISTS assessments (id TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT)")
            else:
                self._memory = {}
        except sqlite3.Error:
            self._memory = {}

    def _conn(self):
        return sqlite3.connect(self.path, timeout=5)

    def get(self, sid: str) -> AssessmentState | None:
        if self._memory is not None:
            raw = self._memory.get(sid)
        else:
            with self._lock, self._conn() as c:
                row = c.execute("SELECT data FROM assessments WHERE id=?", (sid,)).fetchone()
            raw = row[0] if row else None
        return AssessmentState.model_validate_json(raw) if raw else None

    def save(self, state: AssessmentState) -> None:
        state.updated_at = now()
        state.version += 1
        data = state.model_dump_json()
        if self._memory is not None:
            self._memory[state.id] = data
            return
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO assessments (id, data, updated_at) VALUES (?, ?, ?)",
                      (state.id, data, state.updated_at))

    def delete(self, sid: str) -> None:
        if self._memory is not None:
            self._memory.pop(sid, None)
            return
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM assessments WHERE id=?", (sid,))
