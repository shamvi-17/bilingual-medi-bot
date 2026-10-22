"""JSON API for the assessment flow (Flask blueprint, mounted at /api)."""

from __future__ import annotations

import logging
from functools import lru_cache

from flask import Blueprint, jsonify, request
from pydantic import BaseModel, Field, ValidationError
from werkzeug.exceptions import HTTPException

from . import llm, voice
from .engine import get_engine
from .extraction import get_lexicon
from .followup import load_questions, render_question
from .knowledge.store import get_store
from .matcher import load_conditions
from .retrieval import get_retriever
from .state import StateStore

log = logging.getLogger(__name__)
bp = Blueprint("api", __name__, url_prefix="/api")


@lru_cache(maxsize=1)
def store() -> StateStore:
    return StateStore()


class StartIn(BaseModel):
    language: str = Field(default="hi", pattern="^(en|hi)$")


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class AnswerIn(BaseModel):
    question_id: str = Field(min_length=1, max_length=64)
    value: str | int | list[str] | None = None


class SymptomEditIn(BaseModel):
    status: str | None = Field(default=None, pattern="^(present|absent|unsure)$")


class SymptomItem(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    status: str = Field(default="present", pattern="^(present|absent|unsure)$")


class SymptomsIn(BaseModel):
    symptoms: list[SymptomItem] = Field(min_length=1, max_length=30)


class AttributeIn(BaseModel):
    name: str
    value: str | int | float | None = None


class LanguageIn(BaseModel):
    language: str = Field(pattern="^(en|hi)$")


def error(status: int, code: str, message: str, details=None):
    body = {"error": {"code": code, "message": message}}
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def parse(model):
    data = request.get_json(silent=True)
    if data is None:
        data = {}
    return model.model_validate(data)


@bp.errorhandler(ValidationError)
def _validation(e: ValidationError):
    return error(422, "invalid_request", "The request body is not valid.",
                 [{"field": ".".join(map(str, x["loc"])), "problem": x["msg"]} for x in e.errors()])


@bp.errorhandler(ValueError)
def _value(e: ValueError):
    return error(400, "bad_request", str(e))


@bp.errorhandler(Exception)
def _unexpected(e: Exception):
    if isinstance(e, HTTPException):
        return error(e.code or 500, e.name.lower().replace(" ", "_"), e.description or e.name)
    log.exception("Unhandled API error")
    return error(500, "internal_error", "Something went wrong on our side. Your answers are saved; please try again.")


def load(sid: str):
    st = store().get(sid)
    if st is None:
        return None, error(404, "not_found", "This assessment was not found or has expired. Please start a new one.")
    return st, None


def save_and_reply(st, payload: dict, status: int = 200):
    store().save(st)
    payload["version"] = st.version
    return jsonify(payload), status


# ── assessment lifecycle ─────────────────────────────────────────────────────

@bp.post("/assessments")
def start():
    body = parse(StartIn)
    st, payload = get_engine().start(body.language)
    return save_and_reply(st, payload, 201)


@bp.get("/assessments/<sid>")
def get_state(sid):
    st, err = load(sid)
    if err:
        return err
    payload = get_engine().respond(st, [])
    payload["transcript"] = [m.model_dump() for m in st.messages]
    return save_and_reply(st, payload)


@bp.post("/assessments/<sid>/messages")
def post_message(sid):
    body = parse(MessageIn)
    st, err = load(sid)
    if err:
        return err
    return save_and_reply(st, get_engine().message(st, body.text))


@bp.post("/assessments/<sid>/answers")
def post_answer(sid):
    body = parse(AnswerIn)
    st, err = load(sid)
    if err:
        return err
    return save_and_reply(st, get_engine().answer(st, body.question_id, body.value))


@bp.post("/assessments/<sid>/symptoms")
def add_symptoms(sid):
    body = parse(SymptomsIn)
    st, err = load(sid)
    if err:
        return err
    return save_and_reply(st, get_engine().add_symptoms(st, [(x.id, x.status) for x in body.symptoms]))


@bp.route("/assessments/<sid>/symptoms/<symptom_id>", methods=["PUT", "PATCH"])
def edit_symptom(sid, symptom_id):
    body = parse(SymptomEditIn)
    st, err = load(sid)
    if err:
        return err
    if body.status is None:
        return error(422, "invalid_request", "status must be present, absent or unsure (use DELETE to remove).")
    return save_and_reply(st, get_engine().edit_symptom(st, symptom_id, body.status))


@bp.delete("/assessments/<sid>/symptoms/<symptom_id>")
def delete_symptom(sid, symptom_id):
    st, err = load(sid)
    if err:
        return err
    return save_and_reply(st, get_engine().edit_symptom(st, symptom_id, None))


@bp.patch("/assessments/<sid>/attributes")
def edit_attribute(sid):
    body = parse(AttributeIn)
    st, err = load(sid)
    if err:
        return err
    return save_and_reply(st, get_engine().set_attribute(st, body.name, body.value))


@bp.post("/assessments/<sid>/red-flags/<flag_id>/dismiss")
def dismiss_flag(sid, flag_id):
    st, err = load(sid)
    if err:
        return err
    return save_and_reply(st, get_engine().dismiss_flag(st, flag_id))


@bp.patch("/assessments/<sid>/language")
def set_language(sid):
    body = parse(LanguageIn)
    st, err = load(sid)
    if err:
        return err
    return save_and_reply(st, get_engine().set_language(st, body.language))


@bp.post("/assessments/<sid>/assessment")
def produce_assessment(sid):
    st, err = load(sid)
    if err:
        return err
    if not st.present():
        return error(409, "no_symptoms", "Tell me at least one symptom before asking for an assessment.")
    return save_and_reply(st, get_engine().request_assessment(st))


@bp.get("/assessments/<sid>/summary")
def llm_summary(sid):
    st, err = load(sid)
    if err:
        return err
    return jsonify(get_engine().llm_summary(st))


@bp.post("/assessments/<sid>/reset")
def reset(sid):
    st, err = load(sid)
    lang = st.language if st else "hi"
    if st:
        store().delete(sid)
    new, payload = get_engine().start(lang)
    return save_and_reply(new, payload, 201)


# ── evidence & sources ───────────────────────────────────────────────────────

@bp.get("/evidence")
def evidence():
    q = (request.args.get("q") or "").strip()
    if not q:
        return error(422, "invalid_request", "Query parameter q is required.")
    condition = request.args.get("condition")
    if condition and condition not in load_conditions():
        return error(404, "not_found", f"Unknown condition '{condition}'.")
    k = min(int(request.args.get("k", 5)), 10)
    try:
        r = get_retriever()
        hits = r.search(q, k=k, topics=[condition] if condition else None)
    except Exception as e:
        log.exception("retrieval failed")
        return error(503, "retrieval_unavailable", "Evidence search is temporarily unavailable.", str(e)[:200])
    return jsonify({"query": q, "backend": r.backend, "results": [h.to_dict() for h in hits],
                    "note": "Only results marked relevant passed the relevance check."})


@bp.get("/sources")
def sources():
    s = get_store()
    return jsonify({"sources": [s.source_info(sid) for sid in s.sources]})


@bp.get("/sources/<source_id>")
def source(source_id):
    s = get_store()
    info = s.source_info(source_id)
    if not info:
        return error(404, "not_found", f"Unknown source '{source_id}'.")
    info["passages"] = [{"chunk_id": c["chunk_id"], "section": c["section"], "text": c["text"]}
                        for c in s.by_source.get(source_id, [])]
    return jsonify(info)


@bp.get("/meta")
def meta():
    lex = get_lexicon()
    conds = load_conditions()
    return jsonify({
        "conditions": [{"id": k, "name": v["name"]} for k, v in conds.items()],
        "symptoms": [{"id": k, "en": v["en"], "hi": v["hi"], "category": v.get("category")} for k, v in lex.symptoms.items()],
    })


# ── voice ────────────────────────────────────────────────────────────────────

VOICE_MESSAGES = {
    "no_speech": {"en": "I couldn't hear any speech. Please try again closer to the microphone, or type instead.",
                  "hi": "Mujhe kuch sunai nahi diya. Mic ke paas bolkar dobara try karein, ya type karein."},
    "unclear": {"en": "I couldn't make that out reliably. Please say it again, or type it.",
                "hi": "Main theek se samajh nahi paaya. Kripya dobara bolein, ya type karein."},
    "unverified": {"en": "Speech recognition is only partly available right now. Please type your message.",
                   "hi": "Abhi voice pehchaan poori tarah kaam nahi kar rahi. Kripya type karein."},
}


@bp.post("/voice/transcribe")
def voice_transcribe():
    audio = request.files.get("audio")
    lang = "hi" if request.form.get("language") == "hi" else "en"
    hints = []
    sid = request.form.get("session_id")
    if sid:
        st = store().get(sid)
        if st and st.pending_question and st.pending_question in load_questions():
            q = render_question(st.pending_question, lang)
            hints = [o["label"] for o in q["options"]]
    try:
        res = voice.transcribe(audio.read() if audio else b"", (audio.filename if audio else "") or "audio.webm", hints)
    except voice.VoiceError as e:
        status = {"unavailable": 503, "provider_error": 502}.get(e.code, 422)
        return error(status, e.code, str(e))
    body = res.to_dict()
    body["message"] = None if res.accepted else VOICE_MESSAGES[res.reason][lang]
    return jsonify(body)


@bp.get("/health")
def health():
    s = get_store()
    try:
        backend = get_retriever().backend
    except Exception as e:
        backend = f"error: {type(e).__name__}"
    return jsonify({
        "status": "ok" if s.available else "degraded",
        "corpus": {"chunks": len(s.chunks), "sources": len(s.by_source), "error": s.load_error},
        "retrieval": backend,
        "llm": llm.status(),
    })
