"""Red-flag screening. Runs before, and independently of, condition matching.

Rules are data (data/redflags.json). Each hit records which rule fired and the
user's words that triggered it, so the emergency message can say exactly why it
appeared, and the user can correct a misunderstanding.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from .config import DATA_DIR
from .extraction import hinglish_variants, normalise
from .knowledge.store import get_store

LEVEL_ORDER = {"emergency": 3, "urgent": 2, "soon": 1}


@dataclass
class RedFlagHit:
    rule_id: str
    level: str
    matched: str        # user's words, or the symptom combination that fired

    def to_dict(self) -> dict:
        return {"id": self.rule_id, "level": self.level, "matched": self.matched}


class RedFlagRules:
    def __init__(self, data: dict):
        self.contacts = data["emergency_contacts"]
        self.mental_health = data["mental_health_contacts"]
        self.rules = {r["id"]: r for r in data["rules"]}
        self._patterns = {
            r["id"]: [re.compile(rf"(?<![a-z])(?:{hinglish_variants(p)})(?![a-z])") for p in r.get("patterns", [])] for r in data["rules"]
        }
        self._unless = {
            r["id"]: [re.compile(hinglish_variants(p)) for p in r.get("unless", [])] for r in data["rules"]
        }

    def screen_text(self, text: str, present: set[str]) -> list[RedFlagHit]:
        """Check one user message. `present` = symptoms currently recorded as present."""
        raw = normalise(text)
        hits = []
        for rid, rule in self.rules.items():
            body = raw
            for u in self._unless[rid]:
                body = u.sub(" ", body)
            m = next((m for p in self._patterns[rid] if (m := p.search(body))), None)
            if not m:
                continue
            if rule.get("with_any") and not (set(rule["with_any"]) & present):
                continue
            if _negated_flag(body, m.start(), m.end()):
                continue
            hits.append(RedFlagHit(rid, rule["level"], m.group(0)))
        return hits

    def screen_state(self, present: set[str]) -> list[RedFlagHit]:
        """Rules defined on symptom combinations rather than on wording."""
        hits = []
        for rid, rule in self.rules.items():
            if rule.get("all_symptoms") and set(rule["all_symptoms"]) <= present:
                hits.append(RedFlagHit(rid, rule["level"], " + ".join(rule["all_symptoms"])))
            elif rule.get("symptoms") and set(rule["symptoms"]) & present:
                hits.append(RedFlagHit(rid, rule["level"], ", ".join(sorted(set(rule["symptoms"]) & present))))
            elif rule.get("symptoms_any") and set(rule["symptoms_any"]) & present and (
                    not rule.get("with_any") or set(rule["with_any"]) & present):
                hits.append(RedFlagHit(rid, rule["level"], ", ".join(sorted(set(rule["symptoms_any"]) & present))))
        return hits

    def describe(self, rule_id: str, lang: str) -> dict:
        """User-facing description of a rule with resolved, verified citations."""
        rule = self.rules[rule_id]
        store = get_store()
        cites = []
        for ev in rule.get("evidence", []):
            c = store.resolve_quote(ev["source_id"], ev["quote"])
            if c:
                cites.append(c.to_dict())
        return {
            "id": rule_id,
            "level": rule["level"],
            "kind": rule.get("kind", "medical"),
            "label": rule["label"]["hi" if lang == "hi" else "en"],
            "citations": cites,
        }


def _negated_flag(text: str, start: int, end: int) -> bool:
    """'no chest pain', 'seene mein dard nahi hai' should not raise an alarm."""
    before = re.findall(r"[a-z']+", text[max(0, start - 30):start])[-3:]
    after = re.findall(r"[a-z']+", text[end:end + 25])[:3]
    if any(t in ("no", "not", "without", "never", "koi", "na", "nahi") for t in before[-2:]):
        return True
    for t in after:
        if t in ("nahi", "nahin", "nhi", "nai"):
            return True
        if t not in ("hai", "ho", "bhi", "bilkul", "abhi", "toh", "to", "raha", "rahi", "koi"):
            break
    return False


@lru_cache(maxsize=1)
def get_rules() -> RedFlagRules:
    return RedFlagRules(json.loads((DATA_DIR / "redflags.json").read_text()))


def highest_level(hits) -> str | None:
    levels = [h["level"] if isinstance(h, dict) else h.level for h in hits]
    return max(levels, key=lambda l: LEVEL_ORDER.get(l, 0)) if levels else None
