"""Check that every curated citation quote is still present on the live source page.

Medical pages are revised; this detects drift between the ingested corpus and what
users will see when they click a citation. Run periodically (and before re-ingesting):

    python -m medassist.knowledge.verify_live
"""

from __future__ import annotations

import json
import sys
import time

import requests
from bs4 import BeautifulSoup

from ..config import DATA_DIR
from .ingest import HEADERS, PARSERS, SOURCES_FILE, clean


def collect_quotes() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}

    def walk(o):
        if isinstance(o, dict):
            if "source_id" in o and "quote" in o:
                out.setdefault(o["source_id"], set()).add(o["quote"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    for f in ("conditions.json", "redflags.json", "questions.json"):
        walk(json.loads((DATA_DIR / f).read_text()))
    return out


def norm(s: str) -> str:
    return " ".join(clean(s).lower().split())


def main() -> int:
    sources = {s["id"]: s for s in json.loads(SOURCES_FILE.read_text())["sources"]}
    quotes = collect_quotes()
    missing, failed = [], []
    for sid, qs in sorted(quotes.items()):
        src = sources[sid]
        try:
            resp = requests.get(src["url"], headers=HEADERS, timeout=25)
            resp.raise_for_status()
            blocks, _ = PARSERS[src["parser"]](BeautifulSoup(resp.content, "html.parser"))
            page = norm(" ".join(t for _, t in blocks))
        except Exception as e:
            failed.append((sid, f"{type(e).__name__}: {e}"[:120]))
            continue
        gone = [q for q in qs if norm(q) not in page]
        missing.extend((sid, q) for q in gone)
        print(f"{'ok ' if not gone else 'CHG'} {sid:30s} {len(qs) - len(gone)}/{len(qs)} quotes present")
        time.sleep(0.4)
    if failed:
        print("\nCould not fetch:", *failed, sep="\n  ")
    if missing:
        print("\nQuotes no longer on the live page (review the rule, then re-ingest):", *missing, sep="\n  ")
    return 1 if (missing or failed) else 0


if __name__ == "__main__":
    sys.exit(main())
