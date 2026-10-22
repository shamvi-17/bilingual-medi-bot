"""Rule-based symptom extraction for English, Roman-script Hindi and Hinglish.

Produces structured findings (canonical symptom id, present/absent/unsure, the
user's own words) plus duration, onset, progression and severity hints. The
lexicon lives in data/symptoms.json so it can be reviewed without reading code.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from .config import DATA_DIR

BOUNDARY = re.compile(r"[.;!?\n]|,|\b(?:but|lekin|magar|however|parantu|although|though|while|jabki)\b")
# Tokens allowed between a symptom and a following negator: "bukhar bilkul nahi hai"
NEG_FILLER = {"hai", "he", "h", "ho", "hoti", "hota", "bhi", "bilkul", "toh", "to", "abhi", "ab", "koi", "rahi",
              "raha", "rahe", "tha", "thi", "hua", "hui", "aa", "aata", "aati", "is", "was", "at", "all", "really"}
NEGATORS_AFTER = {"nahi", "nahin", "nhi", "nai", "nahi.", "na", "nope"}
NEGATORS_BEFORE = {"no", "not", "without", "never", "nor", "na", "dont", "don't", "didnt", "didn't", "havent",
                   "haven't", "hasnt", "hasn't", "denies", "koi"}
# Tokens allowed between a preceding negator and the symptom: "no fever or cough", "don't have any rash"
PRE_FILLER = {"have", "having", "has", "had", "any", "a", "an", "or", "ya", "nor", "i", "do", "does", "feel",
              "feeling", "get", "getting", "mujhe", "mere", "ko", "signs", "sign", "of", "experience", "experiencing"}
UNSURE = re.compile(r"\b(pata nahi?n?|pata nhi|malum nahi?n?|maloom nahi?n?|not sure|unsure|maybe|shayad|sure nahi?n?|i think|lagta hai)\b")

NUMBER_WORDS = {
    "ek": 1, "one": 1, "a": 1, "an": 1, "do": 2, "two": 2, "teen": 3, "three": 3, "char": 4, "chaar": 4, "four": 4,
    "paanch": 5, "panch": 5, "five": 5, "chhe": 6, "che": 6, "six": 6, "saat": 7, "seven": 7, "aath": 8, "eight": 8,
    "few": 3, "kuch": 3, "couple": 2, "dedh": 1.5, "dhai": 2.5, "several": 4,
}
UNIT_DAYS = {"hour": 1 / 24, "ghant": 1 / 24, "day": 1, "din": 1, "dino": 1, "week": 7, "haft": 7,
             "month": 30, "mahin": 30, "year": 365, "saal": 365, "sal": 365}
DURATION_RE = re.compile(
    r"\b(\d+(?:\.\d+)?|" + "|".join(NUMBER_WORDS) + r")\s*(hours?|ghante?|days?|din|dino|dinon|weeks?|hafte?|hafton|months?|mahine?|mahino|years?|saal|sal)\b")
RELATIVE_DURATIONS = [
    (re.compile(r"\b(since (this )?morning|aaj (subah )?se|subah se|since today|today|aaj hi|kuch ghante)\b"), 0.5),
    (re.compile(r"\b(since yesterday|kal se|kal raat se|yesterday)\b"), 1),
    (re.compile(r"\b(parso se|parson se|day before yesterday)\b"), 2),
    (re.compile(r"\b(last week|pichhle hafte|pichle hafte|ek hafte se|a week)\b"), 7),
    (re.compile(r"\b(last month|pichhle mahine|pichle mahine)\b"), 30),
]
RECURRING_RE = re.compile(r"\b(baar[- ]baar|aksar|often|every (day|morning|night|week)|roz|daily|recurr\w*|keeps? coming back|har (din|roz|hafte|mahine))\b")
ONSET_SUDDEN = re.compile(r"\b(achanak|suddenly|sudden|ekdam|ek ?dum|all of a sudden|out of nowhere)\b")
ONSET_GRADUAL = re.compile(r"\b(dheere[- ]dheere|dhire[- ]dhire|gradually|slowly|over (a few|few|several) days)\b")
WORSENING = re.compile(r"\b(getting worse|worse|worsening|badh (raha|rahi|rahe|gaya|gayi)|zyada ho (raha|rahi|gaya)|bigad\w*)\b")
IMPROVING = re.compile(r"\b(getting better|improv\w*|better now|behtar|kam ho (raha|rahi|gaya|gayi)|theek ho (raha|rahi))\b")
SEVERE = re.compile(r"\b(bahut (tez|zyada|zor)|bohot (tez|zyada)|severe|unbearable|worst|extreme\w*|intense|sehan nahi|bardasht nahi)\b")
MILD = re.compile(r"\b(halka|halki|mild|thoda|thodi|slight\w*|little)\b")

YES_RE = re.compile(r"^\s*(haa?n?|haan ji|ji haa?n?|yes|yeah|yep|yup|ji|sahi|correct|bilkul|ho raha hai|hai)\b")
NO_RE = re.compile(r"^\s*(nahi?n?|nhi|no|nope|na|ji nahi?n?|nahi hai|bilkul nahi)\b")


@dataclass
class Finding:
    symptom: str
    status: str            # present | absent | unsure
    words: str             # the user's original phrase
    start: int = 0
    intensity: str | None = None


@dataclass
class Extraction:
    findings: list[Finding] = field(default_factory=list)
    duration_days: float | None = None
    recurring: bool = False
    onset: str | None = None
    progression: str | None = None
    severity_hint: str | None = None   # "severe" | "mild"
    clarifications: list[str] = field(default_factory=list)
    language: str = "en"
    residual: str = ""

    @property
    def symptom_ids(self) -> set[str]:
        return {f.symptom for f in self.findings}


class Lexicon:
    def __init__(self, data: dict):
        self.symptoms: dict[str, dict] = data["symptoms"]
        self.patterns: list[tuple[str, re.Pattern]] = []
        self.gap_patterns: list[tuple[str, re.Pattern]] = []
        for sid, info in self.symptoms.items():
            for p in info.get("patterns", []):
                target = self.gap_patterns if p.startswith("~") else self.patterns
                target.append((sid, re.compile(rf"(?<![a-z])(?:{hinglish_variants(p.lstrip('~'))})(?![a-z])")))
        self.ambiguous = [
            (name, [re.compile(hinglish_variants(p)) for p in info["patterns"]], info["question"], set(info.get("unless_any", [])),
             bool(info.get("only_if_nothing_found")))
            for name, info in data.get("ambiguous_terms", {}).items() if not name.startswith("_")
        ]

    def label(self, sid: str, lang: str) -> str:
        info = self.symptoms.get(sid)
        if not info:
            return sid.replace("_", " ")
        return info["hi" if lang == "hi" else "en"]

    def category(self, sid: str) -> str:
        return self.symptoms.get(sid, {}).get("category", "other")


@lru_cache(maxsize=1)
def get_lexicon() -> Lexicon:
    return Lexicon(json.loads((DATA_DIR / "symptoms.json").read_text()))


def hinglish_variants(pattern: str) -> str:
    """Accept common spellings of the postposition 'mein' (in): 'mai', 'mei' — "pet mai dard"."""
    return re.sub(r"\bmein\b", "(?:mein|mai|mei)", pattern)


URINE_COMPLAINTS = {"urinary_frequency", "urinary_difficulty", "dark_urine", "blood_in_urine"}

HINGLISH_MARKERS = {"hai", "hain", "mujhe", "mera", "meri", "mere", "nahi", "nahin", "kya", "ho", "raha", "rahi", "se",
                    "mein", "aur", "bhi", "ka", "ki", "ke", "kal", "din", "bahut", "thoda", "ji", "haan", "kuch", "lag",
                    "dard", "takleef", "bukhar", "khansi", "sar", "pet", "naak", "gala", "gale", "jalan", "khujli",
                    "ulti", "taraf", "achanak", "shuru", "hua", "gaya", "gayi", "kab", "kitne"}


def detect_language(text: str) -> str:
    toks = re.findall(r"[a-z]+", text.lower())
    hits = sum(1 for t in toks if t in HINGLISH_MARKERS)
    return "hi" if hits >= 2 or (toks and hits / len(toks) >= 0.2) else "en"


def normalise(text: str) -> str:
    t = text.lower()
    t = t.replace("’", "'").replace("’", "'")
    t = re.sub(r"(.)\1{2,}", r"\1", t)          # "bukharrr" -> "bukhar"
    t = re.sub(r"[^\w\s'.,;!?\-/]", " ", t)
    t = t.replace("-", " ")
    t = re.sub(r"[ \t]+", " ", t)
    return t.strip()


def _clause_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    left = 0
    for m in BOUNDARY.finditer(text, 0, start):
        left = m.end()
    m = BOUNDARY.search(text, end)
    right = m.start() if m else len(text)
    return left, right


def _negated(text: str, start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    left, right = _clause_bounds(text, start, end)
    after = re.findall(r"[a-z']+", text[end:right])
    for tok in after[:5]:
        if tok in NEGATORS_AFTER:
            return True
        if tok not in NEG_FILLER:
            break
    # preceding negation; other symptom phrases in a list ("no fever or cough") are skipped over
    before_text = text[left:start]
    for s, e in spans:
        if left <= s and e <= start:
            before_text = before_text.replace(text[s:e], " ")
    before = re.findall(r"[a-z']+", before_text)
    for tok in reversed(before[-6:]):
        if tok in NEGATORS_BEFORE:
            return True
        if tok not in PRE_FILLER:
            break
    return False


def extract(text: str, lexicon: Lexicon | None = None) -> Extraction:
    lex = lexicon or get_lexicon()
    raw = normalise(text)
    # neutralise "pata nahi" etc. so the "nahi" inside is not read as a negation
    masked = UNSURE.sub(lambda m: "U" * len(m.group(0)), raw)
    result = Extraction(language=detect_language(raw))

    candidates = []
    for sid, pat in lex.patterns:
        for m in pat.finditer(raw):
            candidates.append((m.start(), m.end(), sid))
    # longest match wins; matched spans are consumed
    candidates.sort(key=lambda c: (-(c[1] - c[0]), c[0]))
    taken: list[tuple[int, int, str]] = []
    for s, e, sid in candidates:
        if any(s < te and ts < e for ts, te, _ in taken):
            continue
        taken.append((s, e, sid))
    # second pass: gap patterns on the text not already claimed (spans replaced by a placeholder word)
    claimed = raw
    for s, e, _ in taken:
        claimed = claimed[:s] + "x" * (e - s) + claimed[e:]
    for sid, pat in lex.gap_patterns:
        if any(t[2] == sid for t in taken):
            continue
        for m in pat.finditer(claimed):
            taken.append((m.start(), m.end(), sid))
            break
    taken.sort()
    spans = [(s, e) for s, e, _ in taken]

    latest: dict[str, Finding] = {}
    for s, e, sid in taken:
        left, right = _clause_bounds(masked, s, e)
        clause = masked[left:right]
        if "U" * 4 in clause:
            status = "unsure"
        elif _negated(masked, s, e, spans):
            status = "absent"
        else:
            status = "present"
        window = raw[max(left, s - 25):s]
        intensity = "severe" if SEVERE.search(window) or re.search(r"\b(tez|high|very)\s*$", window) else (
            "mild" if MILD.search(window) else None)
        # later mentions in the same message override earlier ones ("fever hai... actually fever nahi")
        latest[sid] = Finding(sid, status, text_slice(text, raw, s, e), s, intensity)
    for f in list(latest.values()):
        for implied in lex.symptoms.get(f.symptom, {}).get("implies", []):
            if f.status == "present" and implied not in latest:
                latest[implied] = Finding(implied, "present", f.words, f.start, f.intensity)
    result.findings = sorted(latest.values(), key=lambda f: f.start)

    residual = raw
    for s, e in sorted(spans, reverse=True):
        residual = residual[:s] + " " * (e - s) + residual[e:]
    result.residual = residual
    found = {f.symptom for f in result.findings if f.status == "present"}
    # "baar baar peshab aata hai aur jalan bhi": a bare 'jalan' alongside another urine complaint is burning urine
    if found & URINE_COMPLAINTS and "urinary_burning" not in found:
        m = re.search(r"\b(jalan|burning|chubhan)\b", residual)
        if m:
            result.findings.append(Finding("urinary_burning", "present", raw[m.start():m.end()], m.start()))
            found.add("urinary_burning")
            residual = residual[:m.start()] + " " * (m.end() - m.start()) + residual[m.end():]
    for _name, pats, question, unless, only_if_empty in lex.ambiguous:
        if only_if_empty and result.findings:
            continue
        if not (unless & found) and any(p.search(residual) for p in pats):
            result.clarifications.append(question)

    result.duration_days = parse_duration(raw)
    result.recurring = bool(RECURRING_RE.search(raw))
    if ONSET_SUDDEN.search(raw):
        result.onset = "sudden"
    elif ONSET_GRADUAL.search(raw):
        result.onset = "gradual"
    if WORSENING.search(raw):
        result.progression = "worsening"
    elif IMPROVING.search(raw):
        result.progression = "improving"
    if SEVERE.search(raw):
        result.severity_hint = "severe"
    elif MILD.search(raw):
        result.severity_hint = "mild"
    return result


def text_slice(original: str, normalised: str, s: int, e: int) -> str:
    """Return the user's phrase; normalisation keeps length close enough to slice the lowered text."""
    return normalised[s:e]


def parse_duration(raw: str) -> float | None:
    best = None
    for m in DURATION_RE.finditer(raw):
        num, unit = m.group(1), m.group(2)
        n = float(num) if re.match(r"\d", num) else NUMBER_WORDS.get(num, 1)
        days = None
        for key, mult in UNIT_DAYS.items():
            if unit.startswith(key):
                days = n * mult
                break
        if days is not None:
            best = max(best or 0, days)
    if best is None:
        for pat, days in RELATIVE_DURATIONS:
            if pat.search(raw):
                best = days
                break
    return best


def parse_yes_no(text: str) -> str | None:
    t = normalise(text)
    if UNSURE.search(t):
        return "unsure"
    if NO_RE.match(t):
        return "no"
    if YES_RE.match(t):
        return "yes"
    return None
