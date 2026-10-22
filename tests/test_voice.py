"""Voice input: transliteration, the prompt-echo safety cross-check, and spoken answers.

The fake Whisper client replays transcripts recorded from real Groq calls during
development (Hindi/English speech clips, background noise and silence).
"""

import io

import pytest

from medassist import voice
from medassist.followup import match_answer
from medassist.translit import has_devanagari, transliterate


class FakeWhisper:
    """Mimics groq.audio.transcriptions.create: picks the reply by (language, prompted)."""

    def __init__(self, replies, fail=()):
        self.replies, self.fail, self.calls = replies, set(fail), []
        self.audio = self
        self.transcriptions = self

    def create(self, **kw):
        key = (kw.get("language"), "prompt" in kw)
        self.calls.append((kw["model"], key))
        if key in self.fail:
            raise RuntimeError("rate limited")
        return self.replies[key]


def run(replies, **kw):
    return voice.transcribe(b"RIFF....", "clip.wav", client=FakeWhisper(replies, **kw))


# ── transliteration ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("dev,roman", [
    ("नाक बंद है", "naak band hai"),
    ("दर्द", "dard"),
    ("छींक", "chheenk"),
    ("ज़ुकाम", "zukaam"),
    ("मुझे acidity है", "mujhe acidity hai"),
])
def test_transliteration(dev, roman):
    assert transliterate(dev) == roman
    assert has_devanagari(dev) and not has_devanagari(roman)


# ── cross-check ──────────────────────────────────────────────────────────────

def test_hindi_speech_is_accepted_in_roman_script():
    r = run({("en", True): "Mujhe 3 din se bukhar hai, aur sar dard ho raha hai.",
             ("hi", False): "मुझे तीन दिन से बुखार है और सिर में दर्ध हो रहा है।"})
    assert r.accepted and r.text.startswith("Mujhe 3 din se bukhar") and not has_devanagari(r.text)
    assert r.agreement >= 0.74


def test_english_speech_is_accepted():
    s = "I suddenly have chest pain spreading to my left arm."
    r = run({("en", True): s, ("hi", False): s})
    assert r.accepted and r.text == s


@pytest.mark.parametrize("echo,check", [
    ("I have a sore throat, runny nose and fever.", "कर दो"),
    ("I have a sore throat, runny nose and fever. I have a sore throat, runny nose and fever.", "झाल"),
    ("Khaane ke baad seenei, chakkar, saan hai, chakkar, saan hai, khabar hai.", "झाल झाल"),
])
def test_prompt_echo_on_noise_is_rejected(echo, check):
    # real outputs for background noise / silence: the prompted pass invents symptoms
    r = run({("en", True): echo, ("hi", False): check, (None, False): check})
    assert not r.accepted and r.text is None and r.reason == "unclear"


@pytest.mark.parametrize("junk", ["Thank you.", "you", ".", "So."])
def test_known_hallucinations_are_no_speech(junk):
    r = run({("en", True): junk, ("hi", False): junk})
    assert not r.accepted and r.reason == "no_speech"


def test_unverifiable_transcript_is_not_used():
    # if the independent pass fails we cannot rule out an echo, so nothing is returned
    r = run({("en", True): "Mujhe bukhar hai"}, fail={("hi", False)})
    assert not r.accepted and r.reason == "unverified"


def test_borderline_score_gets_a_second_opinion():
    main = "Mera naak band hai, aur gale mein kharash hai, 2 din se."
    fake = FakeWhisper({("en", True): main, ("hi", False): "मेरा नाम", (None, False): "मेरा नाक बंद है और गले में खराश है, दो दिन से"})
    r = voice.transcribe(b"x", "c.webm", client=fake)
    assert r.accepted
    assert (fake.calls[-1][1]) == (None, False)


def test_model_fallback_on_provider_error():
    class Flaky(FakeWhisper):
        def create(self, **kw):
            if kw["model"] == "whisper-large-v3-turbo":
                raise RuntimeError("429")
            return super().create(**kw)
    s = "I have a sore throat"
    fake = Flaky({("en", True): s, ("hi", False): s})
    r = voice.transcribe(b"x", "c.webm", client=fake)
    assert r.accepted and r.model == "whisper-large-v3"


def test_devanagari_main_pass_is_transliterated():
    r = run({("en", True): "मेरा नाक बंद है", ("hi", False): "मेरा नाक बंद है"})
    assert r.accepted and r.text == "meraa naak band hai"


@pytest.mark.parametrize("data,name,code", [(b"", "a.webm", "empty_audio"), (b"x", "a.exe", "bad_format"),
                                            (b"x" * (voice.MAX_BYTES + 1), "a.webm", "too_large")])
def test_upload_validation(data, name, code):
    with pytest.raises(voice.VoiceError) as e:
        voice.transcribe(data, name, client=FakeWhisper({}))
    assert e.value.code == code


def test_question_options_are_added_as_hints():
    p = voice.build_prompt(["Behtar ho rahe hain", "Waise hi hain", "हिंदी"])
    assert "Behtar ho rahe hain" in p and "हिंदी" not in p


# ── spoken answers to the question on screen ─────────────────────────────────

@pytest.mark.parametrize("qid,text,value", [
    ("q_progression", "behtar ho rahe hain", "better"),
    ("q_progression", "getting worse", "worse"),
    ("q_age", "adult", "adult"),
    ("q_duration", "1-3 din", "1to3"),
    ("q_severity", "paanch", 5),
    ("q_severity", "around 7", 7),
    ("q_allergen", "haan", "yes"),
    ("rf_resp", "inme se koi nahi", "none"),
    ("rf_resp", "seene mein dard", ["chest"]),
    ("q_systemic", "bukhar aur badan dard", ["fever", "body_ache"]),
    ("q_headache_location", "dono taraf", "both"),
    ("q_onset", "pata nahi", "unsure"),
])
def test_match_answer(qid, text, value):
    assert match_answer(qid, text) == value


@pytest.mark.parametrize("qid,text", [
    ("q_systemic", "bukhar bhi hai aur 3 din se ho raha hai mujhe"),   # a description, not a checklist answer
    ("q_progression", "mera sar dard ho raha hai"),
    ("q_severity", "bahut zyada"),
])
def test_non_answers_fall_through(qid, text):
    assert match_answer(qid, text) is None


def test_spoken_answer_drives_the_assessment(engine):
    st, r = engine.start("hi")
    r = engine.message(st, "naak band hai aur chheenk aa rahi hai")
    assert r["question"]["id"] == "rf_resp"
    r = engine.message(st, "nahi")                      # answers the safety check
    assert "rf_resp" in st.asked and r["question"]["id"] == "q_age"
    r = engine.message(st, "adult")
    assert st.attributes.age_group == "adult"


def test_spoken_red_flag_option_triggers_emergency(engine):
    st, r = engine.start("hi")
    engine.message(st, "khaansi hai")
    r = engine.message(st, "seene mein dard")
    assert r["stage"] == "emergency"


# ── endpoint ────────────────────────────────────────────────────────────────

def test_voice_endpoint(client, monkeypatch):
    seen = {}

    def fake(audio, filename, hints=None, client=None):
        seen["hints"] = hints
        return voice.VoiceResult("Mujhe bukhar hai", True, None, 0.9, "whisper-large-v3-turbo", "मुझे बुखार है")
    monkeypatch.setattr(voice, "transcribe", fake)
    sid = client.post("/api/assessments", json={"language": "hi"}).json["session_id"]
    client.post(f"/api/assessments/{sid}/messages", json={"text": "naak band hai"})
    r = client.post("/api/voice/transcribe", content_type="multipart/form-data",
                    data={"audio": (io.BytesIO(b"x"), "v.webm"), "language": "hi", "session_id": sid})
    assert r.status_code == 200 and r.json["accepted"] and r.json["text"] == "Mujhe bukhar hai"
    assert seen["hints"], "pending question options should be passed as recognition hints"


def test_voice_endpoint_rejection_message(client, monkeypatch):
    monkeypatch.setattr(voice, "transcribe", lambda *a, **k: voice.VoiceResult(None, False, "unclear", 0.1, "m", "x"))
    r = client.post("/api/voice/transcribe", content_type="multipart/form-data",
                    data={"audio": (io.BytesIO(b"x"), "v.webm"), "language": "en"})
    assert r.status_code == 200 and not r.json["accepted"] and "say it again" in r.json["message"]


def test_voice_endpoint_without_key(client, monkeypatch):
    from medassist.config import settings
    monkeypatch.setattr(settings, "groq_api_key", None)
    r = client.post("/api/voice/transcribe", content_type="multipart/form-data",
                    data={"audio": (io.BytesIO(b"x"), "v.webm")})
    assert r.status_code == 503 and r.json["error"]["code"] == "unavailable"
