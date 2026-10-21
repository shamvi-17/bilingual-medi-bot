import json
from pathlib import Path

import pytest

from medassist.config import DATA_DIR
from medassist.knowledge.store import KnowledgeStore, get_store, text_fragment_url
from medassist.retrieval import Retriever
from conftest import run_flow


def all_evidence(obj, path=""):
    if isinstance(obj, dict):
        if "source_id" in obj and "quote" in obj:
            yield path, obj
        for k, v in obj.items():
            yield from all_evidence(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from all_evidence(v, f"{path}[{i}]")


@pytest.mark.parametrize("fname", ["conditions.json", "redflags.json", "questions.json"])
def test_every_curated_quote_exists_verbatim_in_corpus(fname):
    store = get_store()
    data = json.loads((DATA_DIR / fname).read_text())
    missing = [(p, e["source_id"], e["quote"]) for p, e in all_evidence(data) if not store.resolve_quote(e["source_id"], e["quote"])]
    assert not missing, missing


def test_every_condition_feature_and_red_flag_is_cited():
    conds = json.loads((DATA_DIR / "conditions.json").read_text())["conditions"]
    for cid, c in conds.items():
        assert c.get("description_evidence"), cid
        for f in c["features"]:
            assert f.get("evidence"), (cid, f["symptom"])
        for item in c["self_care"] + c["see_doctor_if"]:
            assert item.get("evidence"), (cid, item["en"])
    rules = json.loads((DATA_DIR / "redflags.json").read_text())["rules"]
    for r in rules:
        if r.get("kind") != "mental_health":
            assert r["evidence"], r["id"]


SCENARIOS = [
    ("en", ["blocked nose, sneezing and a sore throat"]),
    ("hi", ["khaane ke baad seene mein jalan aur khatti dakar"]),
    ("hi", ["sar ke ek taraf dhak dhak dard, ji machal raha hai"]),
    ("en", ["itchy rash with raised bumps after eating prawns"]),
    ("hi", ["4 din se potty nahi hui, bahut zor lagana padta hai"]),
]


@pytest.mark.parametrize("lang,msgs", SCENARIOS)
def test_assessment_citations_resolve_to_chunks_containing_quote(engine, lang, msgs):
    store = get_store()
    _, r = run_flow(engine, lang, msgs)
    a = r["assessment"]
    assert a["status"] == "candidates"
    assert a["validation"]["claims"] == a["validation"]["grounded"] > 0
    assert not a["validation"]["issues"]
    n = 0
    for _, cite in all_evidence(a):
        if "chunk_id" not in cite:
            continue
        chunk = store.chunk(cite["chunk_id"])
        assert chunk is not None
        assert " ".join(cite["quote"].lower().split()) in " ".join(chunk["text"].lower().split())
        assert cite["url"] == store.sources[cite["source_id"]]["url"]
        assert cite["link"].startswith(cite["url"])
        n += 1
    assert n >= 5
    # every supporting symptom shown to the user is one the user actually reported as present
    present = {s["id"] for s in a["reported"]["present"]}
    for c in a["conditions"]:
        for s in c["supporting"]:
            assert s["symptom"] in present


def test_unverifiable_quote_is_dropped_not_shown(engine, monkeypatch):
    from medassist import explain
    st, r = run_flow(engine, "en", ["blocked nose, sneezing and a sore throat"])
    original = explain.load_conditions()
    patched = json.loads(json.dumps(original))
    patched["common_cold"]["features"][0]["evidence"]["quote"] = "this sentence is not in any source"
    monkeypatch.setattr(explain, "load_conditions", lambda: patched)
    a = explain.build_assessment(st, "en")
    assert a["validation"]["grounded"] < a["validation"]["claims"]
    assert any("Unverified citation dropped" in i for i in a["validation"]["issues"])
    shown = [q["citation"]["quote"] for c in a["conditions"] for q in c["supporting"]]
    assert "this sentence is not in any source" not in shown


def test_text_fragment_link():
    assert text_fragment_url("https://x.org/p/", "sneezing") == "https://x.org/p/#:~:text=sneezing"
    long = text_fragment_url("https://x.org/p/", "one two three four five six seven eight nine ten eleven twelve")
    assert "#:~:text=one%20two%20three%20four%20five,ten%20eleven%20twelve" in long


# ── retrieval ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def retriever():
    return Retriever(mode="lexical")


@pytest.mark.parametrize("query,expected_source", [
    ("sneezing itchy watery eyes allergic reaction", "allergic"),
    ("burning feeling in the chest after eating sour taste", "heartburn|indigestion"),
    ("hard lumpy stool straining", "constipation"),
    ("pressing tight band headache both sides", "tension|headache"),
    ("itchy raised rash bumps", "hives"),
])
def test_retrieval_finds_relevant_source(retriever, query, expected_source):
    import re
    hits = retriever.search(query, k=3)
    assert hits and hits[0].relevant
    assert re.search(expected_source, hits[0].chunk["source_id"])


def test_topic_filter(retriever):
    hits = retriever.search("symptoms", k=5, topics=["constipation"])
    assert hits and all("constipation" in h.chunk["topics"] for h in hits)


def test_irrelevant_query_flagged(retriever):
    hits = retriever.search("quantum chromodynamics lattice gauge", k=3)
    assert all(not h.relevant for h in hits)


def test_missing_corpus_degrades_safely(tmp_path, engine, monkeypatch):
    empty = KnowledgeStore(directory=Path(tmp_path))
    assert not empty.available and empty.load_error
    assert Retriever(store=empty, mode="lexical").search("fever") == []
    from medassist import explain
    monkeypatch.setattr(explain, "get_store", lambda: empty)
    st, r = run_flow(engine, "en", ["blocked nose and sneezing"])
    a = explain.build_assessment(st, "en")
    assert a["status"] == "evidence_unavailable" and a["conditions"] == []


def test_freshness_flags():
    from medassist.knowledge.store import freshness
    import datetime as dt
    today = dt.date(2026, 10, 1)
    assert freshness("01 January 2020", today=today)["status"] == "old"
    assert freshness("01 January 2026", today=today)["status"] == "current"
    assert freshness("01 January 2026", "01 June 2026", today=today)["status"] == "review_overdue"
    assert freshness(None, today=today)["status"] == "unknown"
