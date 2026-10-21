"""Optional LLM helpers (Groq). The assessment never depends on them.

The LLM is used for exactly two things, and both outputs are validated:
  1. mapping free text the rule-based extractor did not understand onto the
     *existing* symptom vocabulary (ids must exist, and the quoted words must
     really appear in the user's message);
  2. rephrasing an already-computed, already-cited assessment summary into a
     friendlier paragraph (rejected if it introduces numbers, medicines,
     certainty language or condition names that were not in the input).
If the provider is unavailable, slow or returns malformed output, callers get
None and fall back to deterministic templates.
"""

from __future__ import annotations

import json
import logging
import re
import time

from .config import settings

log = logging.getLogger(__name__)

_client = None
_last_error: str | None = None
_cooldown_until = 0.0

MEDICINE_WORDS = re.compile(
    r"\b(paracetamol|ibuprofen|aspirin|antibiotic\w*|amoxicillin|azithromycin|cetirizine|levocetirizine|"
    r"antihistamine\w*|omeprazole|pantoprazole|ranitidine|famotidine|antacid\w*|laxative\w*|steroid\w*|"
    r"\d+\s?mg|dose|dosage|tablet\w*|capsule\w*|syrup)\b", re.I)
CERTAINTY_WORDS = re.compile(
    r"\b(definitely|certainly|for sure|guarantee\w*|nothing serious|nothing to worry|no need to (see|worry)|"
    r"pakka (hai|se)|chinta ki koi baat nahi)\b", re.I)


def status() -> dict:
    return {
        "configured": bool(settings.groq_api_key),
        "enabled": settings.llm_enabled,
        "models": settings.llm_models,
        "last_error": _last_error,
    }


def _get_client():
    global _client
    if _client is None:
        from groq import Groq
        _client = Groq(api_key=settings.groq_api_key, timeout=settings.llm_timeout, max_retries=0)
    return _client


def chat(messages: list[dict], json_mode: bool = False, max_tokens: int = 600) -> str | None:
    """Try each configured model in order. Returns None on any failure."""
    global _last_error, _cooldown_until
    if not settings.llm_available or time.time() < _cooldown_until:
        return None
    try:
        client = _get_client()
    except Exception as e:
        _last_error = f"client init failed: {e}"[:200]
        return None
    for model in settings.llm_models:
        try:
            kwargs = dict(model=model, messages=messages, max_tokens=max_tokens, temperature=0.2)
            if model.startswith("openai/gpt-oss"):
                kwargs["reasoning_effort"] = "low"
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            resp = client.chat.completions.create(**kwargs)
            text = resp.choices[0].message.content
            if text:
                _last_error = None
                return text
        except Exception as e:
            _last_error = f"{model}: {type(e).__name__}: {e}"[:300]
            log.warning("LLM call failed: %s", _last_error)
            continue
    # every model failed: back off for a minute instead of slowing every request
    _cooldown_until = time.time() + 60
    return None


def parse_json(text: str | None) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def extract_symptoms(text: str, vocabulary: dict[str, str]) -> list[dict]:
    """Map a message onto known symptom ids. Output is validated; hallucinations are dropped."""
    vocab_lines = "\n".join(f"- {sid}: {label}" for sid, label in vocabulary.items())
    system = (
        "You map a patient's message (English, Hindi in Roman script, or Hinglish) onto a fixed list of symptom ids. "
        "Only use ids from the list. Do not infer symptoms that are not stated. For each symptom, copy the exact "
        "words from the message that express it. Mark status 'absent' when the message denies it. "
        'Respond with JSON: {"symptoms": [{"id": "...", "status": "present|absent", "words": "..."}]}'
    )
    user = f"Symptom ids:\n{vocab_lines}\n\nMessage: {text}"
    data = parse_json(chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                           json_mode=True, max_tokens=500))
    out = []
    if not isinstance(data, dict) or not isinstance(data.get("symptoms"), list):
        return out
    low = text.lower()
    for item in data["symptoms"]:
        if not isinstance(item, dict):
            continue
        sid, st, words = item.get("id"), item.get("status"), str(item.get("words", "")).strip()
        if sid in vocabulary and st in ("present", "absent") and words and words.lower() in low:
            out.append({"id": sid, "status": st, "words": words})
    return out


def validate_summary(text: str, allowed_names: list[str], source_text: str) -> list[str]:
    """Return a list of problems; an empty list means the paraphrase may be shown."""
    problems = []
    if re.search(r"\d+\s?%|percent|probability|likelihood of \d", text, re.I):
        problems.append("contains percentages or probabilities")
    numbers = set(re.findall(r"\b\d+\b", text)) - set(re.findall(r"\b\d+\b", source_text))
    if numbers:
        problems.append(f"introduces numbers not in the input: {sorted(numbers)}")
    if MEDICINE_WORDS.search(text) and not MEDICINE_WORDS.search(source_text):
        problems.append("mentions medicines or doses")
    if CERTAINTY_WORDS.search(text):
        problems.append("uses diagnostic certainty language")
    for name in allowed_names:
        short = re.escape(name.split("(")[0].strip().lower())
        if short and re.search(rf"\byou (have|are suffering from|definitely have)\s+(a |an )?{short}", text.lower()):
            problems.append(f"states '{name}' as a diagnosis")
    if len(text) > 900:
        problems.append("too long")
    return problems


def rephrase_summary(facts: str, lang: str, allowed_names: list[str]) -> tuple[str | None, list[str]]:
    language = "natural Hinglish (Hindi in Roman script mixed with simple English medical words)" if lang == "hi" else "plain English"
    system = (
        f"Rewrite the assessment notes below as one short, warm paragraph (max 90 words) in {language} for a non-medical reader. "
        "Use ONLY facts from the notes. Do not add conditions, medicines, doses, numbers, tests or reassurance. "
        "Say these are possibilities, not a diagnosis. Return only the paragraph."
    )
    text = chat([{"role": "system", "content": system}, {"role": "user", "content": facts}], max_tokens=400)
    if not text:
        return None, ["llm unavailable"]
    text = text.strip().strip('"')
    problems = validate_summary(text, allowed_names, facts)
    return (None if problems else text), problems
