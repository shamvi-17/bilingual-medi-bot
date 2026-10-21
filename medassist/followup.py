"""Adaptive follow-up question selection and answer application.

Order of questions:
  1. clarifications for ambiguous words ("dard", "cold", "weakness")
  2. red-flag safety screens for the body areas involved (always, once each)
  3. essential context: who the assessment is for, how long symptoms have lasted
  4. discriminating checklists, chosen by how much their unanswered symptoms
     separate the conditions still under consideration (skipped when they add nothing)
  5. a few context questions only when relevant (onset, severity, progression, risk factors)

Questions already asked, or whose answers are already known from free text, are never repeated.
"""

from __future__ import annotations

import json
from functools import lru_cache

from .config import DATA_DIR, settings
from .extraction import get_lexicon
from .matcher import load_conditions

MAX_DISCRIMINATING = 3


@lru_cache(maxsize=1)
def load_questions() -> dict[str, dict]:
    return json.loads((DATA_DIR / "questions.json").read_text())["questions"]


def options_for(qid: str) -> list[dict]:
    q = load_questions()[qid]
    if "options" in q:
        return q["options"]
    lex = get_lexicon()
    return [{"value": s, "label": {"en": lex.symptoms[s]["en"], "hi": lex.symptoms[s]["hi"]}, "present": [s]}
            for s in q.get("targets", [])]


def _near_candidates(present: set[str]) -> dict[str, dict]:
    """Conditions whose entry requirement is met — the ones a question could still help separate."""
    return {cid: c for cid, c in load_conditions().items() if set(c.get("required_any", [])) & present}


def _symptom_value(sym: str, conds: dict[str, dict]) -> float:
    containing, weight = 0, 0.0
    for c in conds.values():
        roles = {f["symptom"]: f["role"] for f in c["features"]}
        nts = {n["symptom"] for n in c.get("not_typical", [])}
        if sym in roles:
            containing += 1
            weight += 2.0 if roles[sym] == "key" else 1.0
        elif sym in nts:
            containing += 1
            weight += 2.0
    if containing == 0:
        return 0.0
    # a symptom shared by every candidate in the same way separates nothing; still worth a little
    return weight if containing < len(conds) or len(conds) == 1 else weight * 0.4


def question_value(qid: str, status: dict[str, str], present: set[str]) -> float:
    q = load_questions()[qid]
    conds = _near_candidates(present)
    if not conds:
        return 0.0
    targets = q.get("targets") or [s for o in options_for(qid) for s in o.get("present", [])]
    return sum(_symptom_value(t, conds) for t in targets if t not in status)


def categories_of(present: set[str]) -> set[str]:
    lex = get_lexicon()
    return {lex.category(s) for s in present}


def next_question(state) -> str | None:
    qs = load_questions()
    status = {s: e.status for s, e in state.symptoms.items()}
    present = {s for s, st in status.items() if st == "present"}
    asked = set(state.asked)
    attrs = state.attributes
    cats = categories_of(present)

    for qid in state.clarifications:
        if qid not in asked:
            return qid
    if not present:
        return None

    screens = sorted(
        (qid for qid, q in qs.items() if q["kind"] == "screen" and qid not in asked and (
            (q.get("when_categories") and set(q["when_categories"]) & cats) or
            (q.get("requires_present") and set(q["requires_present"]) <= present))),
        key=lambda qid: -qs[qid]["priority"])
    if screens:
        return screens[0]

    if "q_age" not in asked and not attrs.age_group:
        return "q_age"
    if "q_duration" not in asked and attrs.duration_days is None and not attrs.recurring:
        return "q_duration"

    budget_used = sum(1 for a in asked if qs.get(a, {}).get("kind") in ("discriminate", "context"))
    if budget_used >= settings.max_followups:
        return None

    asked_disc = sum(1 for a in asked if qs.get(a, {}).get("kind") == "discriminate")
    if asked_disc < MAX_DISCRIMINATING:
        best, best_val = None, 0.0
        for qid, q in qs.items():
            if q["kind"] != "discriminate" or qid in asked:
                continue
            if q.get("when_categories") and not set(q["when_categories"]) & cats:
                continue
            # a single-choice question whose answer was already given in free text is not asked again
            if q["type"] == "single" and set(q.get("targets", [])) & set(status):
                continue
            val = question_value(qid, status, present)
            # need at least one unanswered key-level symptom's worth of information
            if val >= 2.0 and (val, q["priority"]) > (best_val, qs[best]["priority"] if best else 0):
                best, best_val = qid, val
        if best:
            return best

    conds = _near_candidates(present)
    if ("q_onset" not in asked and not attrs.onset
            and {"common_cold", "flu_like_illness"} <= set(conds)):
        return "q_onset"
    if "q_severity" not in asked and attrs.severity is None:
        return "q_severity"
    if ("q_progression" not in asked and not attrs.progression
            and (attrs.duration_days or 0) >= 3):
        return "q_progression"
    if "q_risk" not in asked and "fever" in present:
        return "q_risk"
    return None


def apply_answer(state, qid: str, value) -> list[str]:
    """Apply a structured answer. Returns red-flag rule ids triggered by the answer."""
    q = load_questions()[qid]
    opts = {o["value"]: o for o in options_for(qid)}
    flags: list[str] = []
    turn = state.turn

    def set_sym(sym: str, st: str):
        state.set_symptom(sym, st, source="answer", words=None, turn=turn)

    def apply_option(o: dict):
        for s in o.get("present", []):
            set_sym(s, "present")
        for s in o.get("absent", []):
            set_sym(s, "absent")
        for k, v in o.get("set", {}).items():
            setattr(state.attributes, k, v)
        if o.get("red_flag"):
            flags.append(o["red_flag"])

    t = q["type"]
    if t == "single":
        if value in opts:
            apply_option(opts[value])
    elif t == "multi":
        selected = [v for v in (value or []) if v in opts]
        none = (value == "none") or (isinstance(value, list) and "none" in value)
        for v in selected:
            apply_option(opts[v])
        if q.get("unchecked_absent") or none:
            chosen = {s for v in selected for s in opts[v].get("present", [])}
            for v, o in opts.items():
                if v in selected:
                    continue
                for s in o.get("present", []):
                    e = state.symptoms.get(s)
                    # an unticked box never overrides something the user explicitly told us
                    if s in chosen or (e and e.status == "present" and e.source in ("text", "edit", "llm")):
                        continue
                    set_sym(s, "absent")
    elif t == "scale":
        try:
            n = int(value)
        except (TypeError, ValueError):
            n = None
        if n is not None:
            state.attributes.severity = max(q.get("min", 1), min(q.get("max", 10), n))
    elif t == "yesno":
        st = {"yes": "present", "no": "absent", "unsure": "unsure"}.get(value)
        if st:
            for s in q.get("targets", []):
                set_sym(s, st)
    if qid not in state.asked:
        state.asked.append(qid)
    state.answers[qid] = value
    if state.pending_question == qid:
        state.pending_question = None
    if qid in state.clarifications:
        state.clarifications.remove(qid)
    return flags


def render_question(qid: str, lang: str, status: dict[str, str] | None = None) -> dict:
    q = load_questions()[qid]
    status = status or {}
    L = "hi" if lang == "hi" else "en"
    out = {
        "id": qid,
        "kind": q["kind"],
        "type": q["type"],
        "text": q["text"][L],
        "why": q["why"][L],
        "options": [{"value": o["value"], "label": o["label"][L]} for o in options_for(qid)],
        "none_option": bool(q.get("none_option")),
        # boxes for symptoms the user already reported are pre-ticked so nothing is asked twice
        "preselected": [o["value"] for o in options_for(qid)
                        if o.get("present") and all(status.get(s) == "present" for s in o["present"])],
    }
    if q["type"] == "scale":
        out.update(min=q["min"], max=q["max"],
                   labels={k: v[L] for k, v in q.get("labels", {}).items()})
    if q["type"] == "yesno":
        out["options"] = [{"value": "yes", "label": "Yes" if L == "en" else "Haan"},
                          {"value": "no", "label": "No" if L == "en" else "Nahi"},
                          {"value": "unsure", "label": "Not sure" if L == "en" else "Pata nahi"}]
    return out
