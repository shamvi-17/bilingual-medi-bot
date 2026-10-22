"""Assessment orchestrator.

Each turn: apply input (free text or structured answer) -> red-flag screening ->
if an emergency is active, stop and show emergency guidance -> otherwise pick the
next useful question -> when none is left (or the user asks), build the cited
assessment. All state lives in AssessmentState, persisted between requests.
"""

from __future__ import annotations

import hashlib

from . import llm
from .explain import build_assessment
from .extraction import Extraction, extract, get_lexicon
from .followup import apply_answer, load_questions, match_answer, next_question, render_question
from .matcher import load_conditions, match_all
from .redflags import get_rules
from .state import AssessmentState, FlagRecord, Message

STEPS = ["symptoms", "safety", "questions", "assessment"]
_summary_cache: dict[str, dict] = {}


def T(lang: str, en: str, hi: str) -> str:
    return hi if lang == "hi" else en


class Engine:
    def __init__(self):
        self.lex = get_lexicon()
        self.rules = get_rules()

    # ── entry points ─────────────────────────────────────────────────────────
    def start(self, language: str = "hi") -> tuple[AssessmentState, dict]:
        st = AssessmentState(language="hi" if language == "hi" else "en")
        greet = T(st.language,
                  "Hi. Tell me what's going on, the way you'd tell a doctor — for example, "
                  "\"blocked nose and a sore throat for two days.\"",
                  "Namaste. Batayein kya takleef hai — waise hi jaise doctor ko batate. "
                  "Maslan: \"2 din se naak band hai aur gale mein dard hai.\"")
        self._say(st, greet, "greeting")
        return st, self.respond(st, [st.messages[-1]])

    def message(self, st: AssessmentState, text: str) -> dict:
        text = (text or "").strip()[:2000]
        st.turn += 1
        st.messages.append(Message(role="user", text=text, turn=st.turn))
        new = []
        before = st.status_map()

        # a short reply to the question on screen ("nahi", "behtar hai", "paanch") answers it,
        # so the assessment can be completed by voice or typing as well as by tapping options
        pending = st.pending_question
        if pending:
            value = match_answer(pending, text)
            if value is not None:
                return self.answer(st, pending, value, echo=False)

        ex = extract(text)
        for f in ex.findings:
            st.set_symptom(f.symptom, f.status, "text", f.words, st.turn, f.intensity)
        if not ex.findings and not ex.clarifications and len(text.split()) >= 2:
            vocab = {s: info["en"] for s, info in self.lex.symptoms.items() if info.get("patterns")}
            for item in llm.extract_symptoms(text, vocab):
                st.set_symptom(item["id"], item["status"], "llm", item["words"], st.turn)
        a = st.attributes
        if ex.duration_days is not None:
            a.duration_days = ex.duration_days
        if ex.recurring:
            a.recurring = True
        if ex.onset:
            a.onset = ex.onset
        if ex.progression:
            a.progression = ex.progression
        if ex.severity_hint:
            a.severity_hint = ex.severity_hint
        for q in ex.clarifications:
            if q not in st.clarifications and q not in st.asked:
                st.clarifications.append(q)
        # free text that answers the pending question's targets counts as answering it
        if pending and pending not in st.asked:
            targets = set(load_questions()[pending].get("targets", []))
            if targets and targets & set(st.status_map()) - set(before):
                st.asked.append(pending)
                st.pending_question = None

        self._screen_texts(st)
        changed = {s: e.status for s, e in st.symptoms.items() if before.get(s) != e.status}
        # after an assessment, new information simply updates it (assessment_requested stays set)
        new.append(self._ack(st, changed, ex))
        return self.respond(st, new)

    def answer(self, st: AssessmentState, qid: str, value, echo: bool = True) -> dict:
        if qid not in load_questions():
            raise ValueError(f"unknown question {qid}")
        if echo:
            st.turn += 1
            st.messages.append(Message(role="user", text=self._answer_text(st, qid, value), turn=st.turn, kind="answer"))
        flags = apply_answer(st, qid, value)
        for fid in flags:
            self._add_flag(st, fid, "answer", self._answer_text(st, qid, value))
        self._screen_texts(st)
        return self.respond(st, [])

    def edit_symptom(self, st: AssessmentState, sid: str, status: str | None) -> dict:
        if sid not in self.lex.symptoms:
            raise ValueError(f"unknown symptom {sid}")
        st.turn += 1
        entry = st.symptoms.get(sid)
        if entry and status != "present":
            # a correction also withdraws warnings raised by the very words being corrected
            for f in st.red_flags:
                if f.source == "text" and any(f.matched in w or w in f.matched for w in entry.user_words):
                    f.dismissed = True
                    if f.id not in st.dismissed_flags:
                        st.dismissed_flags.append(f.id)
        if status is None:
            st.symptoms.pop(sid, None)
            msg = T(st.language, f"Removed: {self.lex.label(sid, 'en')}.", f"Hata diya: {self.lex.label(sid, 'hi')}.")
        else:
            st.set_symptom(sid, status, "edit", None, st.turn)
            word = {"present": ("present", "hai"), "absent": ("not present", "nahi hai"), "unsure": ("not sure", "pata nahi")}[status]
            msg = T(st.language, f"Updated: {self.lex.label(sid, 'en')} — {word[0]}.", f"Update kiya: {self.lex.label(sid, 'hi')} — {word[1]}.")
        self._screen_texts(st)
        return self.respond(st, [self._say(st, msg, "update")])

    def add_symptoms(self, st: AssessmentState, items: list[tuple[str, str]]) -> dict:
        """Structured selections (e.g. the quick-start category picker)."""
        st.turn += 1
        changed = {}
        for sid, status in items:
            if sid not in self.lex.symptoms:
                raise ValueError(f"unknown symptom {sid}")
            st.set_symptom(sid, status, "edit", None, st.turn)
            changed[sid] = status
        labels = ", ".join(self.lex.label(s, st.language) for s, v in changed.items() if v == "present")
        st.messages.append(Message(role="user", text=labels, turn=st.turn, kind="answer"))
        self._screen_texts(st)
        return self.respond(st, [self._ack(st, changed, Extraction())])

    def set_attribute(self, st: AssessmentState, name: str, value) -> dict:
        allowed = {"duration_days": float, "severity": int, "onset": str, "progression": str, "age_group": str}
        if name not in allowed:
            raise ValueError(f"attribute {name} cannot be edited")
        setattr(st.attributes, name, None if value in (None, "") else allowed[name](value))
        st.turn += 1
        return self.respond(st, [self._say(st, T(st.language, "Updated your details.", "Aapki details update kar di."), "update")])

    def dismiss_flag(self, st: AssessmentState, flag_id: str) -> dict:
        if flag_id not in st.dismissed_flags:
            st.dismissed_flags.append(flag_id)
        for f in st.red_flags:
            if f.id == flag_id:
                f.dismissed = True
        msg = T(st.language,
                "Okay, I've noted that this warning sign does not apply. If it does happen, please seek emergency care immediately.",
                "Theek hai, maine note kar liya ki yeh warning sign laagu nahi hota. Agar aisa ho, to turant emergency care lein.")
        return self.respond(st, [self._say(st, msg, "update")])

    def set_language(self, st: AssessmentState, lang: str) -> dict:
        st.language = "hi" if lang == "hi" else "en"
        msg = T(st.language, "Switched to English. Your answers so far are kept.", "Hinglish mein switch kar diya. Ab tak ke jawaab save hain.")
        return self.respond(st, [self._say(st, msg, "update")])

    def request_assessment(self, st: AssessmentState) -> dict:
        st.assessment_requested = True
        st.pending_question = None
        return self.respond(st, [])

    # ── response ─────────────────────────────────────────────────────────────
    def respond(self, st: AssessmentState, new_messages: list) -> dict:
        lang = st.language
        flags = st.active_flags()
        emergency = [f for f in flags if f.level == "emergency"]
        out = {
            "session_id": st.id, "language": lang, "version": st.version + 1,
            "messages": [m.model_dump() if hasattr(m, "model_dump") else m for m in new_messages if m],
            "question": None, "emergency": None, "assessment": None,
            "notices": [self.rules.describe(f.id, lang) | {"matched": f.matched} for f in flags if f.level in ("urgent", "soon")],
            "symptoms": self._symptom_list(st), "attributes": st.attributes.model_dump(),
        }
        present = st.present()
        if emergency:
            st.pending_question = None
            out["stage"] = "emergency"
            out["emergency"] = self._emergency(st, emergency)
        else:
            qid = None if st.assessment_requested else next_question(st)
            if qid:
                st.pending_question = qid
                q = load_questions()[qid]
                out["stage"] = {"screen": "safety", "clarify": "symptoms"}.get(q["kind"], "questions")
                out["question"] = render_question(qid, lang, st.status_map())
                lead = self._lead(st, q)
                if lead:
                    out["messages"].append(self._say(st, lead, "lead").model_dump())
            elif not present and not st.assessment_requested:
                out["stage"] = "symptoms"
            else:
                st.pending_question = None
                st.assessment_requested = True
                out["stage"] = "assessment"
                out["assessment"] = build_assessment(st, lang)
                if not any(m.kind == "assessment_intro" and m.turn == st.turn for m in st.messages):
                    intro = (T(lang, "Here is what I found, with the evidence behind each point.",
                               "Yeh raha aapka assessment — har baat ke saath uska evidence bhi diya gaya hai.")
                             if out["assessment"]["status"] == "candidates" else
                             T(lang, "Here is my summary and what I suggest next.", "Yeh raha summary aur aage kya karna chahiye."))
                    out["messages"].append(self._say(st, intro, "assessment_intro").model_dump())
        out["progress"] = self._progress(st, out["stage"])
        out["can_assess"] = bool(present) and not emergency
        return out

    # ── helpers ──────────────────────────────────────────────────────────────
    def _say(self, st: AssessmentState, text: str, kind: str = "text") -> Message:
        m = Message(role="assistant", text=text, turn=st.turn, kind=kind)
        st.messages.append(m)
        return m

    def _add_flag(self, st: AssessmentState, fid: str, source: str, matched: str) -> None:
        if fid in st.dismissed_flags or any(f.id == fid for f in st.red_flags):
            return
        rule = self.rules.rules[fid]
        st.red_flags.append(FlagRecord(id=fid, level=rule["level"], matched=matched, source=source, turn=st.turn))

    def _screen_texts(self, st: AssessmentState) -> None:
        present = st.present()
        # re-screen all user text so combinations spread over several messages are caught
        for text in st.user_texts():
            for h in self.rules.screen_text(text, present):
                self._add_flag(st, h.rule_id, "text", h.matched)
        for h in self.rules.screen_state(present):
            self._add_flag(st, h.rule_id, "state", h.matched)
        # state-based flags that no longer hold (symptom corrected) are withdrawn
        for f in st.red_flags:
            if f.source == "state" and not any(h.rule_id == f.id for h in self.rules.screen_state(present)):
                f.dismissed = True

    def _symptom_list(self, st: AssessmentState) -> list[dict]:
        lang = st.language
        return [{"id": s, "label": self.lex.label(s, lang), "status": e.status, "user_words": e.user_words,
                 "source": e.source, "category": self.lex.category(s)} for s, e in st.symptoms.items()]

    def _ack(self, st: AssessmentState, changed: dict[str, str], ex) -> Message | None:
        lang = st.language
        if not changed and not ex.clarifications:
            if ex.duration_days is not None or ex.onset or ex.progression:
                return self._say(st, T(lang, "Thanks, noted.", "Shukriya, note kar liya."), "ack")
            st.unrecognised.append(st.user_texts()[-1] if st.user_texts() else "")
            return self._say(st, T(lang,
                "I couldn't recognise a symptom in that. Could you describe it differently? For example: \"headache since yesterday\", \"acidity after meals\", \"itchy rash on arms\".",
                "Main isme koi symptom pehchaan nahi paaya. Kya aap thoda alag tareeke se likh sakte hain? Jaise: \"kal se sar dard\", \"khaane ke baad acidity\", \"haath par khujli wale daane\"."),
                "unrecognised")
        parts = []
        pres = [s for s, v in changed.items() if v == "present"]
        absn = [s for s, v in changed.items() if v == "absent"]
        uns = [s for s, v in changed.items() if v == "unsure"]

        def said(s):
            # echo the user's own words where we have them; fall back to the plain label
            e = st.symptoms[s]
            if e.user_words:
                return e.user_words[-1]
            lab = self.lex.label(s, lang)
            return lab[0].lower() + lab[1:] if lang == "en" else lab

        def listing(items):
            items = list(dict.fromkeys(items))
            if len(items) == 1:
                return items[0]
            return ", ".join(items[:-1]) + T(lang, " and ", " aur ") + items[-1]

        if not (pres or absn or uns):
            return None
        if pres:
            parts.append(T(lang, "Okay — ", "Theek hai — ") + listing([said(s) for s in pres]) + ".")
        if absn:
            parts.append(T(lang, "No ", "") + listing([said(s) for s in absn])
                         + T(lang, ", noted.", " nahi hai, yeh bhi note kar liya."))
        if uns:
            parts.append(T(lang, "Not sure about ", "") + listing([said(s) for s in uns])
                         + T(lang, " — that's fine.", " ke baare mein pakka nahi — koi baat nahi."))
        cands, _ = match_all(st.status_map(), st.attributes.model_dump())
        if cands and not st.active_flags():
            names = [load_conditions()[c.condition_id]["name"]["hi" if lang == "hi" else "en"] for c in cands[:2]]
            j = " ya " if lang == "hi" else " or "
            parts.append(T(lang,
                f"So far it sounds like it could be {j.join(names)}, but it's too early to say which.",
                f"Abhi tak yeh {j.join(names)} jaisa lag raha hai, par itne se pakka nahi keh sakte."))
        return self._say(st, " ".join(p[0].upper() + p[1:] for p in parts if p), "ack")

    def _lead(self, st: AssessmentState, q: dict) -> str | None:
        lang = st.language
        if q["kind"] == "screen":
            return T(lang, "Before anything else, a quick safety check.", "Usse pehle ek zaroori safety check.")
        if q is load_questions()["clarify_general"]:
            return T(lang, "That could mean a lot of different things — the symptoms will tell us more.",
                     "Infection ya tabiyat kharab hona kai cheezon se ho sakta hai — symptoms se zyada pata chalega.")
        if q["kind"] == "clarify":
            return T(lang, "Just so I don't get this wrong —", "Bas yeh pakka kar loon —")
        return None

    def _answer_text(self, st: AssessmentState, qid: str, value) -> str:
        q = render_question(qid, st.language)
        labels = {o["value"]: o["label"] for o in q["options"]}
        if q["type"] == "scale":
            return f"{value}/10"
        if value == "none" or value == ["none"] or (isinstance(value, list) and not value):
            return T(st.language, "None of these", "Inme se koi nahi")
        if isinstance(value, list):
            return ", ".join(labels.get(v, str(v)) for v in value)
        return labels.get(value, str(value))

    def _emergency(self, st: AssessmentState, flags: list[FlagRecord]) -> dict:
        lang = st.language
        L = "hi" if lang == "hi" else "en"
        mental = any(self.rules.rules[f.id].get("kind") == "mental_health" for f in flags)
        reasons = [self.rules.describe(f.id, lang) | {"matched": f.matched} for f in flags]
        return {
            "level": "emergency",
            "title": T(lang, "This may need emergency care", "Yeh emergency ho sakti hai"),
            "instruction": self.rules.mental_health[L] if mental else self.rules.contacts[L],
            "mental_health": mental,
            "reasons": reasons,
            "while_waiting": T(lang,
                "Don't drive yourself. Stay with someone if you can. Keep your phone with you.",
                "Khud gaadi na chalayein. Ho sake to kisi ke saath rahein. Phone apne paas rakhein."),
            "note": T(lang,
                "I've paused the routine assessment because these signs should be checked by a doctor straight away. If I misunderstood, you can tell me below.",
                "Maine routine assessment rok diya hai kyunki in signs ko turant doctor se check karwana chahiye. Agar maine galat samjha ho, to neeche bata sakte hain."),
        }

    def _progress(self, st: AssessmentState, stage: str) -> dict:
        qs = load_questions()
        asked = [a for a in st.asked if qs.get(a, {}).get("kind") != "clarify"]
        idx = {"symptoms": 0, "safety": 1, "questions": 2, "assessment": 3, "emergency": 1}.get(stage, 0)
        return {"stage": stage, "step": idx, "steps": STEPS, "questions_asked": len(asked)}

    # ── optional LLM phrasing ────────────────────────────────────────────────
    def llm_summary(self, st: AssessmentState) -> dict:
        a = build_assessment(st, st.language)
        if a["status"] != "candidates":
            return {"available": False, "reason": "no candidate conditions"}
        facts = [a["summary"]]
        for c in a["conditions"]:
            facts.append(f"{c['name']}: {c['support']['label']}. {c['explanation']}")
        facts.append(f"Next step: {a['urgency']['label']}.")
        facts_text = "\n".join(facts)
        key = hashlib.sha1((facts_text + st.language).encode()).hexdigest()
        if key in _summary_cache:
            return _summary_cache[key]
        text, problems = llm.rephrase_summary(facts_text, st.language, [c["name"] for c in a["conditions"]])
        res = {"available": bool(text), "text": text, "rejected_reasons": problems if not text else [],
               "note": T(st.language, "Rephrased by an AI model from the cited assessment above; check the evidence below.",
                         "Upar diye cited assessment se AI model ne aasaan shabdon mein likha hai; evidence neeche dekhein.")}
        if text or problems != ["llm unavailable"]:
            _summary_cache[key] = res
        return res


_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = Engine()
    return _engine
