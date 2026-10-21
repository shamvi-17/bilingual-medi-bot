"""Read access to the ingested corpus: sources, chunks and verified quotations.

A citation in this project is always a (source_id, quote) pair that must appear
verbatim in one ingested chunk. `resolve_quote` is the single place where that
check happens; anything that cannot be resolved is treated as unverified and is
never shown to the user as evidence.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import KNOWLEDGE_DIR

STALE_AFTER_YEARS = 3


def _norm(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", text).strip().lower()


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    for fmt in ("%d %B %Y", "%Y-%m-%d", "%m/%d/%Y", "%d %b %Y"):
        try:
            return dt.datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


@dataclass(frozen=True)
class Citation:
    source_id: str
    chunk_id: str
    title: str
    publisher: str
    url: str
    section: str
    quote: str
    last_reviewed: str | None

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "chunk_id": self.chunk_id,
            "title": self.title,
            "publisher": self.publisher,
            "url": self.url,
            "link": text_fragment_url(self.url, self.quote),
            "section": self.section,
            "quote": self.quote,
            "last_reviewed": self.last_reviewed,
        }


def text_fragment_url(url: str, quote: str) -> str:
    """Deep link that highlights the quoted text in browsers supporting text fragments.

    Browsers without support simply open the page. Quotes containing characters
    that we normalised during ingestion (quotes/dashes) are linked without a
    fragment, since the fragment would not match the original page text.
    """
    if re.search(r"['\"\-]", quote):
        words = [w for w in re.split(r"\s+", quote) if w]
        # use the longest leading run of words free of normalised characters
        safe = []
        for w in words:
            if re.search(r"['\"\-]", w):
                break
            safe.append(w)
        if len(safe) < 3:
            return url
        quote = " ".join(safe)
    words = quote.rstrip(".").split()
    if len(words) > 10:
        frag = urllib.parse.quote(" ".join(words[:5])) + "," + urllib.parse.quote(" ".join(words[-3:]))
    else:
        frag = urllib.parse.quote(" ".join(words))
    return f"{url}#:~:text={frag}"


class KnowledgeStore:
    def __init__(self, directory: Path = KNOWLEDGE_DIR):
        self.directory = directory
        self.sources: dict[str, dict] = {}
        self.chunks: list[dict] = []
        self.by_source: dict[str, list[dict]] = {}
        self.manifest: dict = {}
        self.load_error: str | None = None
        self._load()

    def _load(self) -> None:
        try:
            registry = json.loads((self.directory / "sources.json").read_text())
            self.sources = {s["id"]: s for s in registry["sources"]}
            corpus = self.directory / "corpus.jsonl"
            for line in corpus.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    rec["_norm"] = _norm(rec["text"])
                    self.chunks.append(rec)
                    self.by_source.setdefault(rec["source_id"], []).append(rec)
            manifest = self.directory / "manifest.json"
            if manifest.exists():
                self.manifest = json.loads(manifest.read_text())
        except Exception as e:  # corpus missing or corrupt: the engine degrades to no-evidence mode
            self.load_error = f"{type(e).__name__}: {e}"
            self.chunks = []

    @property
    def available(self) -> bool:
        return bool(self.chunks)

    def resolve_quote(self, source_id: str, quote: str) -> Citation | None:
        q = _norm(quote)
        for rec in self.by_source.get(source_id, []):
            if q in rec["_norm"]:
                return Citation(
                    source_id=source_id,
                    chunk_id=rec["chunk_id"],
                    title=rec["title"],
                    publisher=rec["publisher"],
                    url=rec["url"],
                    section=rec["section"],
                    quote=quote,
                    last_reviewed=rec.get("last_reviewed"),
                )
        return None

    def chunk(self, chunk_id: str) -> dict | None:
        source_id = chunk_id.split("#")[0]
        for rec in self.by_source.get(source_id, []):
            if rec["chunk_id"] == chunk_id:
                return rec
        return None

    def source_info(self, source_id: str) -> dict | None:
        src = self.sources.get(source_id)
        if not src:
            return None
        man = self.manifest.get(source_id, {})
        chunks = self.by_source.get(source_id, [])
        last_reviewed = man.get("last_reviewed") or (chunks[0].get("last_reviewed") if chunks else None)
        return {
            "id": source_id,
            "title": src["title"],
            "publisher": src["publisher"],
            "url": src["url"],
            "topics": src["topics"],
            "last_reviewed": last_reviewed,
            "next_review_due": man.get("next_review_due"),
            "retrieved": man.get("retrieved") or (chunks[0].get("retrieved") if chunks else None),
            "ingested": bool(chunks),
            "chunks": len(chunks),
            "freshness": freshness(last_reviewed, man.get("next_review_due")),
        }


def freshness(last_reviewed: str | None, next_review_due: str | None = None, today: dt.date | None = None) -> dict:
    """Flag sources that may be outdated so the UI can say so instead of hiding it."""
    today = today or dt.date.today()
    reviewed = parse_date(last_reviewed)
    due = parse_date(next_review_due)
    if due and due < today:
        return {"status": "review_overdue", "note": f"Publisher's planned review date ({next_review_due}) has passed."}
    if reviewed is None:
        return {"status": "unknown", "note": "Review date not available."}
    age_years = (today - reviewed).days / 365.25
    if age_years > STALE_AFTER_YEARS:
        return {"status": "old", "note": f"Last reviewed {last_reviewed}; more than {STALE_AFTER_YEARS} years ago."}
    return {"status": "current", "note": f"Last reviewed {last_reviewed}."}


@lru_cache(maxsize=1)
def get_store() -> KnowledgeStore:
    return KnowledgeStore()
