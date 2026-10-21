"""Run the scenario evaluation and write evaluation/results.md + results.json.

    python -m evaluation.run_eval            # LLM off, lexical retrieval (deterministic)
    RETRIEVAL_MODE=auto python -m evaluation.run_eval

Metrics (software behaviour against source-derived expectations — NOT clinical validation):
  candidate recall      share of expected conditions that appear among the conditions listed
  top-1 agreement       expected top condition is listed first (where one is specified)
  exclusion respected   conditions expected to be set aside are not listed
  red-flag sensitivity  emergency scenarios that reached the emergency stage
  red-flag specificity  non-emergency scenarios that did not
  refusal correctness   scenarios that should not produce a prediction did not
  citation correctness  displayed citations whose quote is found verbatim in the cited chunk and whose URL matches the source
  grounding rate        medical statements in assessments that carry a verified citation
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("MEDASSIST_LLM", "0")
os.environ.setdefault("RETRIEVAL_MODE", "lexical")
os.environ["MEDASSIST_DB"] = ":memory:"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from medassist.engine import Engine  # noqa: E402
from medassist.knowledge.store import get_store  # noqa: E402

HERE = Path(__file__).parent
URGENCY_ORDER = ["self_care", "soon", "urgent", "emergency"]
DEFAULTS = {"q_age": "adult", "q_duration": "1to3", "q_progression": "same", "q_onset": "unsure"}


def drive(engine: Engine, sc: dict):
    st, r = engine.start(sc["lang"])
    for m in sc["messages"]:
        r = engine.message(st, m)
        if r["stage"] == "emergency":
            return st, r
    answers = sc.get("answers", {})
    for _ in range(20):
        q = r["question"]
        if not q:
            break
        if q["id"] in answers:
            v = answers[q["id"]]
        elif q["type"] == "multi":
            v = "none"
        elif q["type"] == "scale":
            v = 3
        elif q["type"] == "yesno":
            v = "no"
        else:
            v = DEFAULTS.get(q["id"], next((o["value"] for o in q["options"] if o["value"] == "unsure"), q["options"][-1]["value"]))
        r = engine.answer(st, q["id"], v)
    return st, r


def citations(obj):
    if isinstance(obj, dict):
        if "chunk_id" in obj and "quote" in obj:
            yield obj
        for v in obj.values():
            yield from citations(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from citations(v)


def main():
    store = get_store()
    scenarios = json.loads((HERE / "scenarios.json").read_text())["scenarios"]
    engine = Engine()
    rows, m = [], {k: [0, 0] for k in ["recall", "top1", "exclude", "sens", "spec", "refuse", "urgency", "cite", "ground", "basis"]}
    for sc in scenarios:
        exp = sc["expect"]
        st, r = drive(engine, sc)
        a = r.get("assessment") or {}
        listed = [c["id"] for c in a.get("conditions", [])] + [c["id"] for c in a.get("more_conditions", [])]
        is_em = r["stage"] == "emergency"
        problems = []
        m["basis"][1] += 1
        if store.resolve_quote(sc["basis"]["source_id"], sc["basis"]["quote"]):
            m["basis"][0] += 1
        else:
            problems.append("basis quote not found in corpus")

        if exp.get("emergency"):
            m["sens"][1] += 1
            fired = [x["id"] for x in (r.get("emergency") or {}).get("reasons", [])]
            if is_em and (not exp.get("red_flag") or exp["red_flag"] in fired):
                m["sens"][0] += 1
            else:
                problems.append(f"expected emergency {exp.get('red_flag')}, got stage={r['stage']} flags={fired}")
        else:
            m["spec"][1] += 1
            if not is_em:
                m["spec"][0] += 1
            else:
                problems.append("unexpected emergency: " + ", ".join(x["id"] for x in r["emergency"]["reasons"]))

        for cid in exp.get("include", []):
            m["recall"][1] += 1
            if cid in listed:
                m["recall"][0] += 1
            else:
                problems.append(f"missing {cid} (listed: {listed})")
        if exp.get("top"):
            m["top1"][1] += 1
            if listed[:1] == [exp["top"]]:
                m["top1"][0] += 1
            else:
                problems.append(f"top was {listed[:1]}, expected {exp['top']}")
        for cid in exp.get("exclude", []):
            m["exclude"][1] += 1
            if cid not in listed:
                m["exclude"][0] += 1
            else:
                problems.append(f"{cid} should have been set aside")
        if exp.get("status"):
            m["refuse"][1] += 1
            if a.get("status") == exp["status"]:
                m["refuse"][0] += 1
            else:
                problems.append(f"status {a.get('status')} != {exp['status']}")
        if exp.get("urgency") or exp.get("urgency_at_least"):
            m["urgency"][1] += 1
            lvl = (a.get("urgency") or {}).get("level")
            ok = lvl == exp["urgency"] if exp.get("urgency") else (
                lvl in URGENCY_ORDER and URGENCY_ORDER.index(lvl) >= URGENCY_ORDER.index(exp["urgency_at_least"]))
            if ok:
                m["urgency"][0] += 1
            else:
                problems.append(f"urgency {lvl}")

        for c in citations([a, r.get("emergency"), r.get("notices")]):
            m["cite"][1] += 1
            chunk = store.chunk(c["chunk_id"])
            if chunk and " ".join(c["quote"].lower().split()) in " ".join(chunk["text"].lower().split()) \
                    and c["url"] == store.sources[c["source_id"]]["url"]:
                m["cite"][0] += 1
            else:
                problems.append(f"bad citation {c['chunk_id']}")
        if a.get("validation"):
            m["ground"][0] += a["validation"]["grounded"]
            m["ground"][1] += a["validation"]["claims"]

        rows.append({"id": sc["id"], "category": sc["category"], "lang": sc["lang"], "stage": r["stage"],
                     "listed": listed, "status": a.get("status"), "urgency": (a.get("urgency") or {}).get("level"),
                     "questions": len(st.asked), "pass": not problems, "problems": problems})

    def pct(k):
        n, d = m[k]
        return f"{n}/{d} ({100 * n / d:.0f}%)" if d else "n/a"

    labels = {"recall": "Candidate-condition recall", "top1": "Top-1 agreement", "exclude": "Set-aside respected",
              "sens": "Red-flag sensitivity (emergency scenarios)", "spec": "Red-flag specificity (non-emergency scenarios)",
              "refuse": "Correct refusal / out-of-scope", "urgency": "Urgency level as expected",
              "cite": "Citation correctness (displayed citations)", "ground": "Evidence-grounding rate (statements)",
              "basis": "Scenario expectations traceable to corpus"}
    summary = {labels[k]: pct(k) for k in labels}
    out = {"generated": dt.datetime.now().isoformat(timespec="seconds"), "retrieval_mode": os.environ.get("RETRIEVAL_MODE"),
           "llm": os.environ.get("MEDASSIST_LLM"), "metrics": summary, "scenarios": rows}
    (HERE / "results.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))

    md = [f"# Evaluation results\n\nGenerated {out['generated']} · retrieval `{out['retrieval_mode']}` · LLM {'off' if out['llm'] == '0' else 'on'} · {len(rows)} scenarios\n",
          "> These numbers measure **software behaviour** against expectations derived from NHS / MedlinePlus / WHO patient pages. "
          "They are **not** a clinical validation: the scenarios and rules were written by the software author and have not been reviewed by clinicians, "
          "and the scenarios are short, scripted cases rather than real patient conversations.\n",
          "| Metric | Result |", "|---|---|"] + [f"| {k} | {v} |" for k, v in summary.items()]
    md += ["", f"Mean follow-up questions per completed scenario: {sum(r['questions'] for r in rows if r['stage'] == 'assessment') / max(1, sum(1 for r in rows if r['stage'] == 'assessment')):.1f}", "",
           "| Scenario | Category | Lang | Stage | Listed conditions | Urgency | Result |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['id']} | {r['category']} | {r['lang']} | {r['stage']} | {', '.join(r['listed']) or '—'} | {r['urgency'] or '—'} | "
                  + ("pass" if r["pass"] else "**fail**: " + "; ".join(r["problems"])) + " |")
    (HERE / "results.md").write_text("\n".join(md) + "\n")
    print("\n".join(f"{k:50s} {v}" for k, v in summary.items()))
    fails = [r for r in rows if not r["pass"]]
    for r in fails:
        print("FAIL", r["id"], r["problems"])
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
