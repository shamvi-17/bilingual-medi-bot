"""The LLM is optional and untrusted: malformed or invented output must never reach the user."""

from medassist import llm
from medassist.config import settings


def test_extract_symptoms_drops_hallucinations(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: (
        '{"symptoms": ['
        '{"id": "fever", "status": "present", "words": "body is burning up"},'      # words appear in message: kept
        '{"id": "cancer", "status": "present", "words": "burning"},'               # unknown id: dropped
        '{"id": "cough", "status": "present", "words": "coughing blood"},'         # words not in message: dropped
        '{"id": "headache", "status": "likely", "words": "burning"}]}'))           # invalid status: dropped
    out = llm.extract_symptoms("my body is burning up", {"fever": "Fever", "cough": "Cough", "headache": "Headache"})
    assert out == [{"id": "fever", "status": "present", "words": "body is burning up"}]


def test_extract_symptoms_handles_malformed_json(monkeypatch):
    for bad in [None, "", "not json at all", '{"symptoms": "oops"}', "[1,2,3]", '{"symptoms": [1, "x", null]}']:
        monkeypatch.setattr(llm, "chat", lambda *a, _b=bad, **k: _b)
        assert llm.extract_symptoms("something odd", {"fever": "Fever"}) == []


def test_summary_validation_rejects_unsafe_paraphrase():
    src = "You reported sneezing and a runny nose. Possible: common cold. Not a diagnosis."
    assert llm.validate_summary("These symptoms can fit a common cold; this is not a diagnosis.", ["Common cold"], src) == []
    assert llm.validate_summary("There is an 80% chance of a cold.", ["Common cold"], src)
    assert llm.validate_summary("Take paracetamol 500 mg twice daily.", ["Common cold"], src)
    assert llm.validate_summary("You definitely have a cold, nothing serious.", ["Common cold"], src)
    assert llm.validate_summary("You have a common cold.", ["Common cold"], src)


def test_rephrase_falls_back_when_validation_fails(monkeypatch):
    monkeypatch.setattr(llm, "chat", lambda *a, **k: "You definitely have a cold. Take 2 tablets.")
    text, problems = llm.rephrase_summary("facts", "en", ["Common cold"])
    assert text is None and problems


def test_unavailable_provider_returns_none(monkeypatch):
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "groq_api_key", None)
    assert llm.chat([{"role": "user", "content": "hi"}]) is None


def test_engine_uses_validated_llm_extraction_only_as_fallback(engine, monkeypatch):
    calls = []

    def fake(text, vocab):
        calls.append(text)
        return [{"id": "fever", "status": "present", "words": "body is burning up"}]
    monkeypatch.setattr(llm, "extract_symptoms", fake)
    st, _ = engine.start("en")
    engine.message(st, "runny nose")                    # understood by rules: no LLM call
    assert calls == []
    engine.message(st, "my body is burning up")         # not understood: LLM fallback, validated
    assert calls == ["my body is burning up"]
    assert st.symptoms["fever"].source == "llm"
