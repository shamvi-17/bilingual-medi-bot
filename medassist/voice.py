"""Speech-to-text for Hinglish and English (Groq Whisper), with a safety cross-check.

Why two passes
--------------
The symptom extractor reads Roman-script text. Whisper in Hindi mode returns
Devanagari (unreadable for the extractor), so the main pass asks for English
output with a Roman-Hinglish example prompt; Whisper then writes Hindi speech as
"Mujhe 3 din se bukhar hai…". But a prompt full of symptom words is dangerous:
on silence or background noise Whisper tends to repeat the prompt, which would
inject symptoms the user never said (observed in testing: noise → "I have a sore
throat, runny nose and fever.").

So every recording is also transcribed *without* a prompt in Hindi mode (which
cannot echo the prompt), transliterated to Roman script, and compared with the
main pass on a loose phonetic key. The main transcript is only accepted when the
two agree; otherwise the user is asked to repeat or type. In testing, real speech
scored 0.74–1.00 and noise/silence echoes 0.02–0.18 (threshold 0.5).
The transcript is always shown to the user for review before it is sent.
"""

from __future__ import annotations

import concurrent.futures as cf
import difflib
import logging
import os
import re
from dataclasses import asdict, dataclass

from .config import settings
from .translit import has_devanagari, transliterate

log = logging.getLogger(__name__)

MODELS = [m.strip() for m in os.environ.get("WHISPER_MODELS", "whisper-large-v3-turbo,whisper-large-v3").split(",") if m.strip()]
MAX_BYTES = 10 * 1024 * 1024
ALLOWED_EXT = {"webm", "ogg", "oga", "wav", "mp3", "m4a", "mp4", "mpeg", "mpga", "flac"}
AGREEMENT_THRESHOLD = 0.5
BORDERLINE = 0.25          # prompt echoes scored <= 0.18 in testing; real speech >= 0.74

# Example sentences teach Whisper to write Hindi speech in Roman script with common symptom spellings.
BASE_PROMPT = (
    "Mujhe 2 din se bukhar hai, sar dard aur badan dard ho raha hai. Naak band hai, naak beh rahi hai, chheenk aa rahi hai, "
    "gale mein kharash hai, khansi nahi hai. Khaane ke baad seene mein jalan, khatti dakar, pet phoola rehta hai, gas, kabz, "
    "ulti, ji machal raha hai, khujli, daane, chakkar, saans phoolna. I have a sore throat, runny nose and fever."
)
# Short, content-free outputs Whisper is known to produce on silence or noise.
HALLUCINATIONS = re.compile(
    r"^(thank you\.?|thanks\.?|thanks for watching\.?|thank you for watching\.?|you\.?|so\.?|bye\.?|the end\.?|"
    r"subscribe\.?|please subscribe\.?|\.+|\s*)$", re.I)


class VoiceError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class VoiceResult:
    text: str | None
    accepted: bool
    reason: str | None
    agreement: float | None
    model: str | None
    check_text: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def phonetic_key(text: str) -> str:
    """Spelling-tolerant comparison key: 'bukhaar'≈'bukhar', 'mein'≈'men', 'chheenk'≈'chink'."""
    s = transliterate(text or "").lower()
    for a, b in (("ee", "i"), ("oo", "u"), ("aa", "a"), ("w", "v"), ("z", "j"), ("q", "k"), ("ph", "f")):
        s = s.replace(a, b)
    s = re.sub(r"([bcdfgjklmnpqrstvxy])h", r"\1", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(r"(.)\1+", r"\1", s)
    return " ".join(s.split())


def agreement(a: str, b: str) -> float:
    ka, kb = phonetic_key(a), phonetic_key(b)
    if not ka or not kb:
        return 0.0
    return difflib.SequenceMatcher(None, ka, kb).ratio()


def build_prompt(hints: list[str] | None = None) -> str:
    """Base prompt plus the labels of the question currently on screen (helps short spoken answers)."""
    prompt = BASE_PROMPT
    if hints:
        extra = ", ".join(h for h in hints if h and not has_devanagari(h))[:300]
        if extra:
            prompt = f"{prompt} {extra}."
    return prompt


def _client():
    from groq import Groq
    return Groq(api_key=settings.groq_api_key, timeout=settings.llm_timeout, max_retries=0)


def _whisper(client, audio: bytes, filename: str, language: str | None, prompt: str | None) -> tuple[str, str]:
    last = None
    for model in MODELS:
        try:
            kw = dict(file=(filename, audio), model=model, response_format="text", temperature=0)
            if language:
                kw["language"] = language
            if prompt:
                kw["prompt"] = prompt
            r = client.audio.transcriptions.create(**kw)
            return (r if isinstance(r, str) else getattr(r, "text", "")).strip(), model
        except Exception as e:  # try the next model
            last = e
            log.warning("Whisper %s failed: %s", model, str(e)[:200])
    raise VoiceError("provider_error", f"Speech recognition failed: {type(last).__name__}")


def validate_upload(audio: bytes, filename: str) -> None:
    if not audio:
        raise VoiceError("empty_audio", "No audio was received.")
    if len(audio) > MAX_BYTES:
        raise VoiceError("too_large", "The recording is too long. Please keep it under a minute.")
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        raise VoiceError("bad_format", f"Unsupported audio format '{ext}'.")


def transcribe(audio: bytes, filename: str = "audio.webm", hints: list[str] | None = None,
               client=None) -> VoiceResult:
    """Return a Roman-script transcript, or accepted=False with a reason the UI can show."""
    validate_upload(audio, filename)
    if client is None:
        if not settings.groq_api_key:
            raise VoiceError("unavailable", "Voice input needs a Groq API key on the server.")
        client = _client()
    prompt = build_prompt(hints)
    with cf.ThreadPoolExecutor(max_workers=2) as ex:
        main_f = ex.submit(_whisper, client, audio, filename, "en", prompt)
        check_f = ex.submit(_whisper, client, audio, filename, "hi", None)
        main_text, model = main_f.result()
        try:
            check_text, _ = check_f.result()
        except VoiceError:
            check_text = None

    if has_devanagari(main_text):          # occasionally Whisper ignores the requested script
        main_text = transliterate(main_text)
    main_text = re.sub(r"\s+", " ", main_text).strip()

    if HALLUCINATIONS.match(main_text):
        return VoiceResult(None, False, "no_speech", None, model, check_text)
    if check_text is None:
        # without the independent pass we cannot rule out a prompt echo, so we don't guess
        return VoiceResult(None, False, "unverified", None, model, None)
    if HALLUCINATIONS.match(check_text):
        return VoiceResult(None, False, "no_speech", 0.0, model, check_text)
    score = agreement(main_text, check_text)
    if BORDERLINE <= score < AGREEMENT_THRESHOLD:
        # a borderline score is usually a bad check pass, not an echo: get one more independent opinion
        try:
            retry_text, _ = _whisper(client, audio, filename, None, None)
            if not HALLUCINATIONS.match(retry_text):
                score = max(score, agreement(main_text, retry_text))
        except VoiceError:
            pass
    if score < AGREEMENT_THRESHOLD:
        return VoiceResult(None, False, "unclear", round(score, 2), model, check_text)
    return VoiceResult(main_text, True, None, round(score, 2), model, check_text)
