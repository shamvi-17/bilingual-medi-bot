"""Conservative, rule-based condition matching.

No probabilities are computed. A condition is only *considered* when the user
reports at least one of its characteristic (key) features, and its qualitative
support level comes from explicit counting rules that are shown to the user:

  stronger match : >= 2 key features, >= 3 matching features in total, nothing that argues against it
  partial match  : >= 1 key feature, >= 2 matching features, at most one thing that argues against it
  limited match  : anything else that still has a key feature

A condition is set aside (shown as "less likely", never as "ruled out") when the
findings against it are at least as many as its key features.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

from .config import DATA_DIR

LEVELS = ("stronger", "partial", "limited")


@dataclass
class ConditionMatch:
    condition_id: str
    level: str | None                     # stronger | partial | limited | None (set aside)
    key_present: list[str] = field(default_factory=list)
    supporting_present: list[str] = field(default_factory=list)
    against: list[dict] = field(default_factory=list)      # {"symptom"|"attribute", ...}
    key_unknown: list[str] = field(default_factory=list)
    supporting_unknown: list[str] = field(default_factory=list)
    key_absent: list[str] = field(default_factory=list)
    unexplained: list[str] = field(default_factory=list)
    score: int = 0

    @property
    def matched(self) -> list[str]:
        return self.key_present + self.supporting_present


@lru_cache(maxsize=1)
def load_conditions() -> dict[str, dict]:
    return json.loads((DATA_DIR / "conditions.json").read_text())["conditions"]


def in_scope_symptoms() -> set[str]:
    out = set()
    for c in load_conditions().values():
        out.update(f["symptom"] for f in c["features"])
    return out


def match_condition(cid: str, cond: dict, status: dict[str, str], attrs: dict) -> ConditionMatch | None:
    present = {s for s, st in status.items() if st == "present"}
    absent = {s for s, st in status.items() if st == "absent"}
    if not set(cond.get("required_any", [])) & present:
        return None
    m = ConditionMatch(cid, None)
    feature_syms = set()
    for f in cond["features"]:
        s = f["symptom"]
        feature_syms.add(s)
        bucket_present = m.key_present if f["role"] == "key" else m.supporting_present
        if s in present:
            bucket_present.append(s)
        elif s in absent:
            if f["role"] == "key":
                m.key_absent.append(s)
        else:
            (m.key_unknown if f["role"] == "key" else m.supporting_unknown).append(s)
    if not m.key_present:
        return None

    for nt in cond.get("not_typical", []):
        if nt["symptom"] in present:
            m.against.append({"type": "symptom", "symptom": nt["symptom"], "note": nt["note"], "evidence": nt["evidence"]})

    days = attrs.get("duration_days")
    if days is not None and cond.get("max_typical_days") and days > cond["max_typical_days"]:
        m.against.append({"type": "duration", "days": days, "evidence": cond.get("duration_evidence"),
                          "note": {"en": f"Symptoms for about {fmt_days(days, 'en')} is longer than this usually lasts.",
                                   "hi": f"Lagbhag {fmt_days(days, 'hi')} se symptoms hain — yeh aam taur par isse jaldi theek ho jaata hai."}})
    onset = cond.get("onset")
    if onset and attrs.get("onset") and attrs["onset"] != onset["expected"]:
        m.against.append({"type": "onset", "onset": attrs["onset"], "evidence": onset["evidence"],
                          "note": {"en": f"Your symptoms started {attrs['onset']}ly; the source describes a {onset['expected']} onset.",
                                   "hi": "Aapke symptoms jis tarah shuru hue, woh source mein bataye gaye tareeke se alag hai."}})
    # absence of a feature the condition requires most (e.g. no fever for flu) counts against
    for s in m.key_absent:
        if s in cond.get("required_any", []) and len(cond["required_any"]) == 1:
            m.against.append({"type": "absent", "symptom": s, "note": None, "evidence": None})

    scope = in_scope_symptoms()
    m.unexplained = sorted(s for s in present if s not in feature_syms and s in scope)

    k, total, a = len(m.key_present), len(m.matched), len(m.against)
    if a >= max(k, 1) and a >= 2:
        m.level = None
    elif k >= 2 and total >= 3 and a == 0:
        m.level = "stronger"
    elif k >= 1 and total >= 2 and a <= 1:
        m.level = "partial"
    else:
        m.level = "limited"
    # duration that clearly exceeds the typical course caps the level
    if m.level == "stronger" and any(x["type"] == "duration" for x in m.against):
        m.level = "partial"
    m.score = 3 * k + len(m.supporting_present) - 2 * a
    return m


def match_all(status: dict[str, str], attrs: dict) -> tuple[list[ConditionMatch], list[ConditionMatch]]:
    """Return (candidates ranked best-first, set-aside conditions)."""
    conds = load_conditions()
    cands, aside = [], []
    for cid, cond in conds.items():
        m = match_condition(cid, cond, status, attrs)
        if m is None:
            continue
        (cands if m.level else aside).append(m)
    order = {lvl: i for i, lvl in enumerate(LEVELS)}
    cands.sort(key=lambda m: (order[m.level], -m.score, -len(m.key_present)))
    return cands, aside


def fmt_days(days: float, lang: str) -> str:
    if days < 1:
        return "less than a day" if lang == "en" else "ek din se kam"
    if days < 14:
        n = round(days)
        return f"{n} day{'s' if n != 1 else ''}" if lang == "en" else f"{n} din"
    if days < 60:
        n = round(days / 7)
        return f"{n} weeks" if lang == "en" else f"{n} hafte"
    n = round(days / 30)
    return f"{n} months" if lang == "en" else f"{n} mahine"
