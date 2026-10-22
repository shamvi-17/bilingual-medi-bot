import os
import sys
from pathlib import Path

# Deterministic test environment: no network LLM calls, fast lexical retrieval, in-memory DB.
os.environ["MEDASSIST_LLM"] = "0"
os.environ.setdefault("RETRIEVAL_MODE", "lexical")
os.environ["MEDASSIST_DB"] = ":memory:"
os.environ["MEDASSIST_WARMUP"] = "0"

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402


@pytest.fixture
def engine():
    from medassist.engine import Engine
    return Engine()


@pytest.fixture
def client():
    from app import app
    app.config["TESTING"] = True
    return app.test_client()


def run_flow(engine, lang, messages, answers=None, default_multi="none"):
    """Drive an assessment: send messages, then answer every question (scripted or default)."""
    answers = answers or {}
    st, r = engine.start(lang)
    for m in messages:
        r = engine.message(st, m)
    guard = 0
    while r["question"] and guard < 20:
        q = r["question"]
        if q["id"] in answers:
            v = answers[q["id"]]
        elif q["type"] == "multi":
            v = default_multi
        elif q["type"] == "scale":
            v = 3
        elif q["type"] == "yesno":
            v = "no"
        else:
            v = {"q_age": "adult", "q_duration": "1to3", "q_progression": "same", "q_onset": "unsure"}.get(
                q["id"], q["options"][-1]["value"])
        r = engine.answer(st, q["id"], v)
        guard += 1
    return st, r
