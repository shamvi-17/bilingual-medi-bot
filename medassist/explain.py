"""Explanation engine: turns the structured state + rule matches into a cited, plain-language assessment.

Every medical statement in the output is attached to a citation that has been
resolved against the ingested corpus (see knowledge/store.py). A statement whose
citation cannot be resolved is dropped and reported under `validation.issues`
instead of being shown without evidence.
"""

from __future__ import annotations

from .extraction import get_lexicon
from .knowledge.store import get_store
from .matcher import ConditionMatch, fmt_days, in_scope_symptoms, load_conditions, match_all
from .redflags import get_rules
from .retrieval import get_retriever

MAX_SHOWN = 3

LEVEL_TEXT = {
    "stronger": {"en": "Matches several typical features", "hi": "Kaafi typical symptoms milte hain"},
    "partial": {"en": "Matches some features", "hi": "Kuch symptoms milte hain"},
    "limited": {"en": "Limited match", "hi": "Thode hi symptoms milte hain"},
}
URGENCY_TEXT = {
    "emergency": {"en": "Emergency — get help now", "hi": "Emergency — abhi madad lein"},
    "urgent": {"en": "Get medical advice today", "hi": "Aaj hi doctor se salah lein"},
    "soon": {"en": "Book a doctor's appointment", "hi": "Doctor ko dikhayein (agle kuch dinon mein)"},
    "self_care": {"en": "Self-care is usually suitable — watch for warning signs", "hi": "Aam taur par ghar par dekhbhaal kaafi hai — warning signs par nazar rakhein"},
}

# Evidence behind the general "see a doctor sooner" rules.
ESCALATION_EVIDENCE = {
    "fever_3_days": {"source_id": "nhs-common-cold", "quote": "you have a high temperature for more than 3 days"},
    "very_unwell": {"source_id": "nhs-flu", "quote": "you feel very unwell"},
    "worse_resp": {"source_id": "nhs-common-cold", "quote": "your cold symptoms get worse"},
    "worse_head": {"source_id": "nhs-headaches", "quote": "you've tried treating a headache yourself and it's not getting better or is getting worse"},
    "worse_other": {"source_id": "nhs-stomach-ache", "quote": "it gets much worse"},
    "cough_3_weeks": {"source_id": "nhs-common-cold", "quote": "you have a cough for more than 3 weeks"},
    "cold_10_days": {"source_id": "nhs-common-cold", "quote": "your cold symptoms do not get better after 10 days"},
    "long_skin": {"source_id": "nhs-itchy-skin", "quote": "does not get better with self care or keeps coming back"},
    "long_stomach": {"source_id": "nhs-stomach-ache", "quote": "it does not go away or keeps coming back"},
    "regular_headache": {"source_id": "nhs-headaches", "quote": "you regularly get headaches"},
    "pregnant": {"source_id": "nhs-flu", "quote": "you're pregnant or have recently given birth"},
    "longterm": {"source_id": "nhs-flu", "quote": "you have a long-term medical condition"},
    "immune": {"source_id": "nhs-flu", "quote": "you have a weakened immune system"},
    "older": {"source_id": "nhs-flu", "quote": "you're 65 or over"},
}


class Builder:
    def __init__(self, state, lang: str):
        self.state = state
        self.L = "hi" if lang == "hi" else "en"
        self.store = get_store()
        self.lex = get_lexicon()
        self.conds = load_conditions()
        self.claims = 0
        self.grounded = 0
        self.issues: list[str] = []
        self.used_sources: set[str] = set()

    # ── helpers ─────────────────────────────────────────────────────────────
    def t(self, d: dict | str | None) -> str:
        if d is None:
            return ""
        return d if isinstance(d, str) else d.get(self.L) or d.get("en", "")

    def label(self, sid: str) -> str:
        return self.lex.label(sid, self.L)

    def cite(self, ev: dict | None, claim: str = "") -> dict | None:
        if not ev:
            return None
        self.claims += 1
        c = self.store.resolve_quote(ev["source_id"], ev["quote"])
        if c is None:
            self.issues.append(f"Unverified citation dropped ({ev['source_id']}): {claim or ev['quote'][:60]}")
            return None
        self.grounded += 1
        self.used_sources.add(c.source_id)
        return c.to_dict()

    def join(self, items: list[str], lower: bool = True) -> str:
        # lower-case the first letter of mid-sentence symptom labels ("Naak band hona" -> "naak band hona")
        items = [i[0].lower() + i[1:] if lower and i and not i[:2].isupper() else i for i in items if i]
        if not items:
            return ""
        if len(items) == 1:
            return items[0]
        conj = " aur " if self.L == "hi" else " and "
        return ", ".join(items[:-1]) + conj + items[-1]

    # ── condition card ───────────────────────────────────────────────────────
    def condition_card(self, m: ConditionMatch, cands: list[ConditionMatch]) -> dict:
        cond = self.conds[m.condition_id]
        st = self.state
        supporting = []
        for f in cond["features"]:
            if f["symptom"] in m.matched:
                cit = self.cite(f["evidence"], f"{f['symptom']} supports {m.condition_id}")
                if cit is None:
                    continue
                e = st.symptoms.get(f["symptom"])
                supporting.append({
                    "symptom": f["symptom"], "label": self.label(f["symptom"]),
                    "user_words": e.user_words if e else [],
                    "role": f["role"],
                    "role_label": ({"key": "Typical feature", "supporting": "Can also occur"} if self.L == "en"
                                   else {"key": "Typical lakshan", "supporting": "Ho bhi sakta hai"})[f["role"]],
                    "citation": cit,
                })
        against = []
        for a in m.against:
            if a["type"] == "absent":
                against.append({"label": self.label(a["symptom"]),
                                "note": (f"You said you do not have {self.label(a['symptom']).lower()}, which this condition is usually expected to include."
                                         if self.L == "en" else f"Aapne bataya ki {self.label(a['symptom'])} nahi hai, jo is condition mein aam taur par hota hai."),
                                "citation": None})
                continue
            cit = self.cite(a.get("evidence"), f"against {m.condition_id}")
            if cit is None:
                continue
            lab = self.label(a["symptom"]) if a.get("symptom") else (
                ("Duration" if self.L == "en" else "Kitne din se") if a["type"] == "duration" else ("How it started" if self.L == "en" else "Kaise shuru hua"))
            against.append({"label": lab, "note": self.t(a["note"]), "citation": cit})

        absent_notes = [self.label(s) for s in m.key_absent]
        unknown = [self.label(s) for s in m.key_unknown] + [self.label(s) for s in m.supporting_unknown[:2]]
        unexplained = [self.label(s) for s in m.unexplained]

        alternatives = []
        cand_ids = {c.condition_id for c in cands}
        for alt in cond.get("alternatives", []):
            if alt not in self.conds:
                continue
            alt_feats = {f["symptom"] for f in self.conds[alt]["features"]}
            shared = [self.label(s) for s in m.matched if s in alt_feats]
            if alt in cand_ids or shared:
                alternatives.append({
                    "id": alt, "name": self.t(self.conds[alt]["name"]),
                    "considered": alt in cand_ids,
                    "why": (f"Shares {self.join(shared[:3]).lower()}." if shared else "Has overlapping symptoms.") if self.L == "en"
                    else (f"Isme bhi {self.join(shared[:3])} hota hai." if shared else "Iske symptoms bhi milte-julte hain."),
                })

        self_care = [{"text": self.t(x), "citation": c} for x in cond.get("self_care", [])
                     if (c := self.cite(x["evidence"], "self-care"))]
        see_doctor = [{"text": self.t(x), "citation": c} for x in cond.get("see_doctor_if", [])
                      if (c := self.cite(x["evidence"], "safety-net"))]
        desc_cit = self.cite(cond.get("description_evidence"), f"description of {m.condition_id}")
        context = None
        if cond.get("context_note"):
            cn = cond["context_note"]
            context = {"text": self.t(cn), "citation": self.cite(cn.get("evidence"), "context note")}

        k = [s["label"] for s in supporting if s["role"] == "key"]
        sp = [s["label"] for s in supporting if s["role"] == "supporting"]
        publishers = sorted({s["citation"]["publisher"].split(" (")[0] for s in supporting})
        pub = self.join(publishers, lower=False) or "the sources"
        if self.L == "en":
            rule = (f"{len(k)} typical feature{'s' if len(k) != 1 else ''}" + (f" and {len(sp)} other possible feature{'s' if len(sp) != 1 else ''}" if sp else "")
                    + f" of {self.t(cond['name'])} match what you reported" + (f"; {len(against)} finding{'s' if len(against) != 1 else ''} point{'s' if len(against) == 1 else ''} elsewhere." if against else "; nothing you reported argues against it."))
            expl = f"You reported {self.join([s['label'].lower() for s in supporting])}. {pub} {'list' if len(publishers) > 1 else 'lists'} {'these' if len(supporting) > 1 else 'this'} among the symptoms of {self.t(cond['name']).lower()}."
            if against:
                expl += f" However, {self.join([a['label'].lower() for a in against])} {'fits' if len(against) == 1 else 'fit'} less well."
            if unknown:
                expl += f" I don't yet know about {self.join([u.lower() for u in unknown[:3]])}."
        else:
            rule = (f"{self.t(cond['name'])} ke {len(k)} typical lakshan" + (f" aur {len(sp)} doosre sambhavit lakshan" if sp else "")
                    + " aapke bataye symptoms se milte hain" + (f"; {len(against)} baat kisi aur wajah ki taraf ishaara karti hai." if against else "; aapki batayi koi baat iske khilaaf nahi jaati."))
            expl = f"Aapne {self.join([s['label'] for s in supporting])} bataya hai. {pub} ke anusaar yeh {self.t(cond['name'])} ke symptoms mein shamil hai."
            if against:
                expl += f" Lekin {self.join([a['label'] for a in against])} isse kam match karta hai."
            if unknown:
                expl += f" Abhi mujhe {self.join(unknown[:3])} ke baare mein nahi pata."

        clarify = []
        if unknown:
            clarify.append((f"Whether you have: {self.join(unknown[:4])}" if self.L == "en" else f"Kya aapko yeh bhi hai: {self.join(unknown[:4])}"))
        if self.state.attributes.duration_days is None:
            clarify.append("How long the symptoms have lasted" if self.L == "en" else "Symptoms kitne din se hain")
        clarify.append("An examination by a doctor, who can check things a symptom checker cannot" if self.L == "en"
                       else "Doctor ka check-up — jo cheezein symptom checker nahi dekh sakta, doctor dekh sakte hain")

        return {
            "id": m.condition_id,
            "name": self.t(cond["name"]),
            "description": self.t(cond["description"]),
            "description_citation": desc_cit,
            "support": {"level": m.level, "label": self.t(LEVEL_TEXT[m.level]), "rule": rule},
            "explanation": expl,
            "supporting": supporting,
            "against": against,
            "absent": absent_notes,
            "unknown": unknown,
            "unexplained": unexplained,
            "clarify": clarify,
            "alternatives": alternatives,
            "context_note": context,
            "self_care": self_care,
            "see_doctor_if": see_doctor,
            "related_passages": self.related(m, cond),
        }

    def related(self, m: ConditionMatch, cond: dict) -> list[dict]:
        """Additional retrieved passages for context; only those passing the relevance check."""
        try:
            retr = get_retriever()
        except Exception as e:  # retrieval failure must not break the assessment
            self.issues.append(f"Retrieval unavailable: {type(e).__name__}")
            return []
        # query with canonical English labels: Roman-script Hinglish retrieves poorly even with multilingual embeddings
        query = cond["name"]["en"] + " symptoms " + " ".join(self.lex.label(s, "en") for s in m.matched)
        hits = retr.search(query, k=4, topics=[m.condition_id], exclude_sections=r"pharmacist|treatment from a gp|GP may prescribe")
        out = []
        for h in hits:
            if h.relevant:
                d = h.to_dict()
                self.used_sources.add(d["source_id"])
                out.append(d)
            if len(out) == 2:
                break
        return out

    # ── urgency ─────────────────────────────────────────────────────────────
    def urgency(self, cards: list[dict], status: str) -> dict:
        st, a = self.state, self.state.attributes
        present = st.present()
        rules = get_rules()
        reasons = []
        level = "self_care"

        def add(lvl: str, text: str, ev_key: str | None = None, citations: list | None = None):
            nonlocal level
            order = ["self_care", "soon", "urgent", "emergency"]
            if order.index(lvl) > order.index(level):
                level = lvl
            cits = citations if citations is not None else ([c] if ev_key and (c := self.cite(ESCALATION_EVIDENCE[ev_key], ev_key)) else [])
            reasons.append({"level": lvl, "text": text, "citations": cits})

        for f in st.active_flags():
            if f.level in ("urgent", "soon"):
                d = rules.describe(f.id, self.L)
                self.claims += len(rules.rules[f.id].get("evidence", []))
                self.grounded += len(d["citations"])
                for c in d["citations"]:
                    self.used_sources.add(c["source_id"])
                add(f.level, d["label"], citations=d["citations"])

        days = a.duration_days
        cats = {self.lex.category(s) for s in present}
        if "fever" in present and days is not None and days > 3:
            add("soon", "Fever for more than 3 days" if self.L == "en" else "3 din se zyada bukhar", "fever_3_days")
        if "fever" in present and a.risk_pregnant:
            add("urgent", "Fever while pregnant or recently given birth" if self.L == "en" else "Pregnancy / haal ki delivery ke saath bukhar", "pregnant")
        if "fever" in present and a.risk_longterm:
            add("urgent", "Fever with a long-term medical condition" if self.L == "en" else "Lambi bimari ke saath bukhar", "longterm")
        if "fever" in present and a.risk_immune:
            add("urgent", "Fever with weakened immunity" if self.L == "en" else "Kamzor immunity ke saath bukhar", "immune")
        if "fever" in present and a.age_group == "older":
            add("urgent", "Flu-like symptoms at age 65 or over" if self.L == "en" else "65+ umar mein flu jaise symptoms", "older")
        if (a.severity or 0) >= 7 or a.severity_hint == "severe":
            add("soon", "You rated your symptoms as severe" if self.L == "en" else "Aapne takleef ko tez bataya hai", "very_unwell")
        if a.progression == "worsening":
            key = "worse_head" if "head" in cats else ("worse_resp" if cats & {"nose", "throat", "chest", "general"} else "worse_other")
            add("soon", "Symptoms are getting worse" if self.L == "en" else "Symptoms badh rahe hain", key)
        if days is not None:
            if "cough" in present and days > 21:
                add("soon", "Cough for more than 3 weeks" if self.L == "en" else "3 hafte se zyada khaansi", "cough_3_weeks")
            elif cats & {"nose", "throat"} and days > 10 and not any(c["id"] == "allergic_rhinitis" for c in cards[:1]):
                add("soon", "Cold-like symptoms for more than 10 days" if self.L == "en" else "10 din se zyada cold jaise symptoms", "cold_10_days")
            elif "skin" in cats and days > 14:
                add("soon", "Skin symptoms lasting more than 2 weeks" if self.L == "en" else "2 hafte se zyada skin ki takleef", "long_skin")
            elif cats & {"stomach", "bowel"} and days > 14:
                add("soon", "Stomach symptoms that are not going away" if self.L == "en" else "Pet ki takleef jo theek nahi ho rahi", "long_stomach")
        if a.recurring and "head" in cats:
            add("soon", "Headaches that keep coming back" if self.L == "en" else "Baar-baar hone wala sar dard", "regular_headache")
        if status in ("insufficient", "age_out_of_scope", "evidence_unavailable"):
            add("soon", {
                "insufficient": "Your symptoms are outside what this tool can assess" if self.L == "en" else "Aapke symptoms is tool ke scope se bahar hain",
                "age_out_of_scope": "This tool is not designed for children under 12" if self.L == "en" else "Yeh tool 12 saal se chhote bachchon ke liye nahi hai",
                "evidence_unavailable": "Medical sources could not be loaded" if self.L == "en" else "Medical sources load nahi ho paaye",
            }[status], citations=[])
        oos = sorted(present - in_scope_symptoms() - {"other_pain"})
        if oos:
            add("soon", (f"Some symptoms are outside this tool's scope: {self.join([self.label(s).lower() for s in oos])}" if self.L == "en"
                         else f"Kuch symptoms is tool ke scope se bahar hain: {self.join([self.label(s) for s in oos])}"), citations=[])
        return {"level": level, "label": self.t(URGENCY_TEXT[level]), "reasons": reasons}

    # ── summary ─────────────────────────────────────────────────────────────
    def summary(self, status: str, cards: list[dict]) -> str:
        present = [self.label(s) for s in self.state.present() if s in in_scope_symptoms()]
        names = [c["name"] for c in cards]
        if status == "candidates":
            if self.L == "hi":
                return (f"Aapke bataye symptoms mein {self.join(present[:4])} shamil hain. Inke basis par kuch common causes possible hain — "
                        f"jaise {self.join(names[:2])}. Lekin sirf symptoms se exact cause confirm nahi kiya ja sakta; yeh diagnosis nahi hai. "
                        "Neeche har possibility ke liye bataya gaya hai ki kaunse symptoms match karte hain, kaunse nahi, aur iska source kya hai.")
            return (f"You reported {self.join([p.lower() for p in present[:4]])}. Based on this, some common causes are possible — "
                    f"such as {self.join(names[:2])}. Symptoms alone cannot confirm the exact cause, and this is not a diagnosis. "
                    "Below, each possibility shows which of your symptoms fit, which don't, and the source for each point.")
        if status == "insufficient":
            return ("Jo information mili hai, woh is tool mein shamil common conditions se itni match nahi karti ki koi possible cause bataya ja sake. "
                    "Isliye main koi andaaza nahi lagaunga — doctor se salah lena behtar hoga." if self.L == "hi" else
                    "The information so far does not match the common conditions this tool covers closely enough to suggest a cause, "
                    "so I won't guess. Please speak to a doctor about these symptoms.")
        if status == "age_out_of_scope":
            return ("Yeh tool 12 saal se chhote bachchon ke symptoms assess karne ke liye nahi bana hai. Bachchon mein symptoms alag tarah se dikh sakte hain — kripya doctor ya pediatrician se salah lein." if self.L == "hi"
                    else "This tool is not designed to assess children under 12, whose symptoms can present differently. Please consult a doctor or paediatrician.")
        if status == "evidence_unavailable":
            return ("Medical sources abhi load nahi ho paaye, isliye main bina evidence ke koi possible cause nahi bataunga. Kripya doctor se salah lein." if self.L == "hi"
                    else "The medical sources could not be loaded, so I will not suggest causes without evidence. Please consult a doctor.")
        return ""

    def build(self) -> dict:
        st = self.state
        present = st.present()
        if not self.store.available:
            status, cands, aside = "evidence_unavailable", [], []
        elif st.attributes.age_group == "child":
            status, cands, aside = "age_out_of_scope", [], []
        else:
            cands, aside = match_all(st.status_map(), st.attributes.model_dump())
            status = "candidates" if cands else "insufficient"
        cards = [self.condition_card(m, cands) for m in cands[:MAX_SHOWN]]
        more = [{"id": m.condition_id, "name": self.t(self.conds[m.condition_id]["name"]),
                 "support": self.t(LEVEL_TEXT[m.level])} for m in cands[MAX_SHOWN:]]
        set_aside = [{"id": m.condition_id, "name": self.t(self.conds[m.condition_id]["name"]),
                      "reasons": [self.t(a["note"]).rstrip(".") if a.get("note") else self.label(a.get("symptom", "")) for a in m.against]}
                     for m in aside]
        urgency = self.urgency(cards, status)

        srcs = [self.store.source_info(s) for s in sorted(self.used_sources)]
        a = st.attributes
        reported = {
            "present": [{"id": s, "label": self.label(s), "user_words": st.symptoms[s].user_words} for s in st.symptoms if st.symptoms[s].status == "present"],
            "absent": [{"id": s, "label": self.label(s)} for s in st.symptoms if st.symptoms[s].status == "absent"],
            "unsure": [{"id": s, "label": self.label(s)} for s in st.symptoms if st.symptoms[s].status == "unsure"],
            "duration": fmt_days(a.duration_days, self.L) if a.duration_days is not None else ("recurring" if a.recurring else None),
            "severity": a.severity, "onset": a.onset, "progression": a.progression, "age_group": a.age_group,
        }
        limitations = ([
            "This is not a diagnosis. It compares your answers with public health information; it cannot examine you or run tests.",
            "It only covers a few common, lower-risk conditions. Other causes — including serious ones — are not ruled out.",
            "The symptom–condition rules were written from NHS, MedlinePlus and WHO patient pages and have not been reviewed by a clinician.",
            "Most sources are UK/US patient information; Indian guidance (MoHFW/NHP) could not be ingested yet.",
        ] if self.L == "en" else [
            "Yeh diagnosis nahi hai. Yeh aapke jawaabon ko public health information se compare karta hai; yeh aapko examine ya test nahi kar sakta.",
            "Isme sirf kuch common, kam-risk wali conditions shamil hain. Doosri wajahein — serious bhi — rule out nahi hui hain.",
            "Symptom–condition rules NHS, MedlinePlus aur WHO ke patient pages se banaye gaye hain; inhe kisi doctor ne review nahi kiya hai.",
            "Zyada tar sources UK/US ke hain; Indian guidance (MoHFW/NHP) abhi shamil nahi ho paayi.",
        ])
        return {
            "status": status,
            "summary": self.summary(status, cards),
            "summary_source": "template",
            "urgency": urgency,
            "reported": reported,
            "conditions": cards,
            "more_conditions": more,
            "set_aside": set_aside,
            "method": ("Conditions are only listed when at least one of their typical features was reported. "
                       "'Matches several typical features' = 2+ typical features and 3+ matching symptoms with nothing against; "
                       "'Matches some features' = 1+ typical feature and 2+ matching symptoms; otherwise 'Limited match'. "
                       "No percentages are calculated because the rules are not clinically calibrated.") if self.L == "en" else
                      ("Koi condition tabhi dikhayi jaati hai jab uska kam se kam ek typical lakshan bataya gaya ho. "
                       "'Kaafi typical symptoms milte hain' = 2+ typical lakshan aur kul 3+ milte symptoms, koi baat khilaaf nahi; "
                       "'Kuch symptoms milte hain' = 1+ typical lakshan aur 2+ milte symptoms; warna 'Thode hi symptoms milte hain'. "
                       "Percentage nahi nikala jaata kyunki yeh rules clinically calibrated nahi hain."),
            "limitations": limitations,
            "sources": [s for s in srcs if s],
            "validation": {"claims": self.claims, "grounded": self.grounded, "issues": self.issues},
        }


def build_assessment(state, lang: str) -> dict:
    return Builder(state, lang).build()
