"""
Ingestion pipeline for the medical RAG corpus.

Fetches every page listed in sources.json, extracts the main clinical text with a
publisher-specific parser, cleans it, splits it into section-aware chunks and writes
corpus.jsonl (one chunk per line) plus a manifest describing what was fetched.

Text is stored verbatim (whitespace-normalised only) so that citations shown to
users can be checked against the original page. Nothing is paraphrased by an LLM.

Run:  python -m medassist.knowledge.ingest            # fetch all sources
      python -m medassist.knowledge.ingest --only nhs-flu
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup, Tag

HERE = Path(__file__).parent
SOURCES_FILE = HERE / "sources.json"
CORPUS_FILE = HERE / "corpus.jsonl"
MANIFEST_FILE = HERE / "manifest.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36 MedAssist-ingest/1.0"
    ),
    "Accept": "text/html",
}

MAX_CHUNK_CHARS = 900
MIN_CHUNK_CHARS = 60

# Section headings that are navigation or site furniture rather than medical content.
SKIP_SECTIONS = re.compile(
    r"^(video|related|more in|help us improve|page last reviewed|references?|"
    r"start here|learn more|see, play and learn|research|resources|journal articles|"
    r"clinical trials|find an expert|patient handouts|related health topics|"
    r"related issues|specifics|images|multimedia|related information|"
    r"genetics|statistics and research|children|teenagers|women|men|older adults|"
    r"who response|treatment and care|prevention and control)\b",
    re.I,
)

LIST_TAGS = ("ul", "ol")
SKIP_TAGS = ("script", "style", "nav", "button", "form", "figure", "noscript", "figcaption")
# image credits, gallery thumbnails and caption text are not clinical content
NOISE = re.compile(r"https?://|\(thumbnail\)|PHOTO LIBRARY|Stock Photo|shutterstock|Skin Deep", re.I)
FOOTER = re.compile(r"^(Page last reviewed|Next review due|Watch this video)", re.I)


def clean(text: str) -> str:
    text = text.replace(" ", " ").replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── Block extraction ───────────────────────────────────────────────────────────

def _blocks_from(root: Tag, heading_tags=("h2", "h3")) -> list[tuple[str, str]]:
    """Walk root in document order and return (section_heading, text_block) pairs.

    Paragraphs and list items are emitted as separate blocks so that a chunk keeps
    the sentence that introduces a list ("The main symptoms include:") together
    with the list items that follow it.
    """
    blocks: list[tuple[str, str]] = []
    section = ""
    sub = ""
    for el in root.descendants:
        if not isinstance(el, Tag):
            continue
        if el.find_parent(SKIP_TAGS) or el.name in SKIP_TAGS:
            continue
        if el.name in heading_tags:
            text = clean(el.get_text(" "))
            if el.name == heading_tags[0]:
                section, sub = text, ""
            else:
                sub = text
            continue
        if el.name == "p" and not el.find_parent(("li",)):
            text = clean(el.get_text(" "))
            if text:
                blocks.append((_heading(section, sub), text))
        elif el.name == "li" and el.find_parent(LIST_TAGS):
            # skip list items that contain nested lists (their children are emitted separately)
            if el.find(LIST_TAGS):
                continue
            text = clean(el.get_text(" "))
            if text:
                blocks.append((_heading(section, sub), "- " + text))
    return blocks


def _heading(section: str, sub: str) -> str:
    section = re.sub(r"^(Non-urgent advice|Urgent advice|Immediate action required):\s*", r"\1: ", section)
    return f"{section} > {sub}" if sub else section


def parse_nhs(soup: BeautifulSoup) -> tuple[list[tuple[str, str]], dict]:
    main = soup.find("main") or soup.body
    article = main.find("article") or main
    for junk in article.select(".nhsuk-review-date, .nhsuk-related-links, .app-related-links, .nhsuk-contents-list, .nhsuk-pagination, .nhsuk-inset-text--video"):
        junk.decompose()
    h1 = soup.find("h1")
    blocks = _blocks_from(article)
    # NHS care cards ("See a GP if", "Call 999 if") use h2/h3 inside a card wrapper; already handled by walk.
    html = str(soup)
    meta = {}
    m = re.search(r"Page last reviewed:\s*([0-9]{1,2} \w+ [0-9]{4})", html)
    if m:
        meta["last_reviewed"] = m.group(1)
    m = re.search(r"Next review due:\s*([0-9]{1,2} \w+ [0-9]{4})", html)
    if m:
        meta["next_review_due"] = m.group(1)
    if h1:
        meta["page_title"] = clean(h1.get_text(" "))
    return blocks, meta


def parse_medlineplus_topic(soup: BeautifulSoup) -> tuple[list[tuple[str, str]], dict]:
    summary = soup.find(id="topic-summary")
    blocks: list[tuple[str, str]] = []
    if summary:
        section = "Summary"
        for el in summary.find_all(["h3", "h2", "p", "li"]):
            if el.name in ("h2", "h3"):
                section = clean(el.get_text(" "))
                continue
            if el.name == "li" and el.find(LIST_TAGS):
                continue
            text = clean(el.get_text(" "))
            if text:
                blocks.append((section, ("- " + text) if el.name == "li" else text))
    meta = {}
    for m in soup.find_all("meta"):
        if m.get("name") == "DC.Date.Modified" and m.get("content"):
            meta["last_reviewed"] = m["content"]
    return blocks, meta


def parse_medlineplus_ency(soup: BeautifulSoup) -> tuple[list[tuple[str, str]], dict]:
    article = soup.find(id="d-article") or soup.body
    blocks: list[tuple[str, str]] = []
    summary = article.find(id="ency_summary")
    if summary:
        for p in summary.find_all("p"):
            text = clean(p.get_text(" "))
            if text:
                blocks.append(("Summary", text))
    for sec in article.select("div.section"):
        title_el = sec.find(["h2", "h3"])
        title = clean(title_el.get_text(" ")) if title_el else ""
        body = sec.find(class_="section-body")
        if not body:
            continue
        for el in body.find_all(["p", "li"]):
            if el.name == "li" and el.find(LIST_TAGS):
                continue
            text = clean(el.get_text(" "))
            if text:
                blocks.append((title, ("- " + text) if el.name == "li" else text))
    meta = {}
    m = re.search(r"Review Date\s*([0-9/]+)", soup.get_text(" "))
    if m:
        meta["last_reviewed"] = m.group(1)
    return blocks, meta


def parse_who_factsheet(soup: BeautifulSoup) -> tuple[list[tuple[str, str]], dict]:
    body = soup.select_one(".sf-detail-body-wrapper") or soup.find("article") or soup.body
    blocks = _blocks_from(body)
    meta = {}
    d = soup.select_one(".date")
    if d:
        m = re.search(r"[0-9]{1,2} \w+ [0-9]{4}", d.get_text(" "))
        if m:
            meta["last_reviewed"] = m.group(0)
    return blocks, meta


PARSERS = {
    "nhs": parse_nhs,
    "medlineplus_topic": parse_medlineplus_topic,
    "medlineplus_ency": parse_medlineplus_ency,
    "who_factsheet": parse_who_factsheet,
}


# ── Chunking ───────────────────────────────────────────────────────────────────

def chunk_blocks(blocks: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Group consecutive blocks of the same section into chunks of <= MAX_CHUNK_CHARS.

    Chunks never cross section boundaries, so a "Call 999 if" list is never merged
    into a self-care section and vice versa.
    """
    chunks: list[tuple[str, str]] = []
    cur_sec, cur = None, []

    def flush():
        if cur:
            text = "\n".join(cur)
            if len(text) >= MIN_CHUNK_CHARS or cur_sec:
                chunks.append((cur_sec or "", text))

    for sec, text in blocks:
        if SKIP_SECTIONS.match(sec or "") or FOOTER.match(text) or NOISE.search(text):
            continue
        size = sum(len(t) + 1 for t in cur)
        if sec != cur_sec or size + len(text) > MAX_CHUNK_CHARS:
            flush()
            # carry the lead-in sentence into the next chunk when a long list is split
            carry = [cur[0]] if (sec == cur_sec and cur and not cur[0].startswith("- ")) else []
            cur_sec, cur = sec, carry
        cur.append(text)
    flush()
    return [(s, t) for s, t in chunks if len(t) >= 25]


def ingest_source(src: dict, session: requests.Session) -> tuple[list[dict], dict]:
    resp = session.get(src["url"], headers=HEADERS, timeout=25)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")
    blocks, meta = PARSERS[src["parser"]](soup)
    chunks = chunk_blocks(blocks)
    retrieved = dt.date.today().isoformat()
    records = []
    for i, (section, text) in enumerate(chunks):
        records.append({
            "chunk_id": f"{src['id']}#{i}",
            "source_id": src["id"],
            "title": src["title"],
            "publisher": src["publisher"],
            "url": src["url"],
            "section": section,
            "text": text,
            "topics": src["topics"],
            "priority": src.get("priority", 2),
            "last_reviewed": meta.get("last_reviewed"),
            "retrieved": retrieved,
        })
    info = {
        "status": "ok",
        "chunks": len(records),
        "last_reviewed": meta.get("last_reviewed"),
        "next_review_due": meta.get("next_review_due"),
        "retrieved": retrieved,
    }
    return records, info


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="*", help="source ids to (re)fetch; others are kept from the existing corpus")
    args = ap.parse_args(argv)

    sources = json.loads(SOURCES_FILE.read_text())["sources"]
    existing: dict[str, list[dict]] = {}
    if args.only and CORPUS_FILE.exists():
        for line in CORPUS_FILE.read_text().splitlines():
            r = json.loads(line)
            existing.setdefault(r["source_id"], []).append(r)
    manifest = json.loads(MANIFEST_FILE.read_text()) if (args.only and MANIFEST_FILE.exists()) else {}

    out: list[dict] = []
    session = requests.Session()
    for src in sources:
        if args.only and src["id"] not in args.only:
            out.extend(existing.get(src["id"], []))
            continue
        try:
            records, info = ingest_source(src, session)
            if not records:
                info = {"status": "empty", "chunks": 0}
            out.extend(records)
            print(f"[ok]   {src['id']:32s} {len(records):3d} chunks  reviewed={info.get('last_reviewed')}")
        except Exception as e:  # keep going; record the failure honestly
            info = {"status": "failed", "error": f"{type(e).__name__}: {e}"[:200], "chunks": 0}
            print(f"[fail] {src['id']:32s} {info['error']}", file=sys.stderr)
            out.extend(existing.get(src["id"], []))
        manifest[src["id"]] = {"url": src["url"], **info}
        time.sleep(0.5)

    with CORPUS_FILE.open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))
    failed = [k for k, v in manifest.items() if v.get("status") != "ok"]
    print(f"\nWrote {len(out)} chunks from {len(sources) - len(failed)} sources to {CORPUS_FILE}")
    if failed:
        print("Not ingested:", ", ".join(failed))


if __name__ == "__main__":
    main()
