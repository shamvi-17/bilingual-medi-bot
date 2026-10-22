import json
import re

from medassist.matcher import match_all
from conftest import run_flow


def asked_sequence(engine, lang, msg, answers=None):
    st, r = engine.start(lang)
    r = engine.message(st, msg)
    seq = []
    answers = answers or {}
    while r["question"] and len(seq) < 20:
        q = r["question"]
        seq.append(q["id"])
        v = answers.get(q["id"], "none" if q["type"] == "multi" else 3 if q["type"] == "scale" else "no" if q["type"] == "yesno"
                       else {"q_age": "adult", "q_duration": "1to3"}.get(q["id"], q["options"][-1]["value"]))
        r = engine.answer(st, q["id"], v)
    return seq, r


# ── adaptive follow-up relevance ─────────────────────────────────────────────

def test_headache_gets_headache_questions_only(engine):
    seq, _ = asked_sequence(engine, "en", "I have a headache")
    assert seq[0] == "rf_head", "safety screen must come first"
    assert {"q_headache_location", "q_headache_quality"} & set(seq)
    assert not {"q_nose_more", "q_stomach_more", "q_skin_look", "q_bowel"} & set(seq)


def test_nasal_symptoms_get_nasal_questions(engine):
    seq, _ = asked_sequence(engine, "hi", "naak beh rahi hai aur chheenk aa rahi hai")
    assert seq[0] == "rf_resp"
    assert "q_nose_more" in seq
    assert not {"q_headache_location", "q_bowel", "q_skin_look"} & set(seq)


def test_no_question_repeated_and_bounded(engine):
    seq, _ = asked_sequence(engine, "en", "runny nose, sore throat, fever and headache")
    assert len(seq) == len(set(seq))
    assert len(seq) <= 12


def test_known_answers_not_asked_again(engine):
    # duration and one-sided throbbing pain are already given in free text
    seq, _ = asked_sequence(engine, "hi", "3 din se sar ke ek taraf dhak dhak dard")
    assert "q_duration" not in seq
    assert "q_headache_location" not in seq and "q_headache_quality" not in seq


def test_checklist_preselects_reported_symptoms(engine):
    st, r = engine.start("en")
    r = engine.message(st, "sneezing and blocked nose")
    r = engine.answer(st, "rf_resp", "none")
    while r["question"]["id"] != "q_nose_more":
        q = r["question"]
        r = engine.answer(st, q["id"], {"q_age": "adult", "q_duration": "1to3"}[q["id"]])
    assert set(r["question"]["preselected"]) >= {"sneezing", "blocked_nose"}


def test_unticked_checklist_never_overrides_free_text(engine):
    st, r = engine.start("en")
    engine.message(st, "sneezing and blocked nose")
    engine.answer(st, "q_nose_more", ["itchy_eyes"])
    assert st.symptoms["sneezing"].status == "present"
    assert st.symptoms["coloured_mucus"].status == "absent"


def test_free_text_yes_answers_pending_yesno(engine):
    st, r = run_flow(engine, "en", ["sneezing, runny nose and itchy eyes"], answers={})
    st2, r = engine.start("en")
    r = engine.message(st2, "sneezing and itchy nose")
    for _ in range(10):
        if r["question"] and r["question"]["id"] == "q_allergen":
            break
        q = r["question"]
        r = engine.answer(st2, q["id"], "none" if q["type"] == "multi" else {"q_age": "adult", "q_duration": "1to3"}.get(q["id"], "unsure"))
    assert r["question"]["id"] == "q_allergen"
    engine.message(st2, "haan")
    assert st2.symptoms["allergen_trigger"].status == "present"


# ── conservative matching ────────────────────────────────────────────────────

def cands(status, attrs=None):
    c, aside = match_all(status, attrs or {})
    return [m.condition_id for m in c], {m.condition_id: m for m in c}, [m.condition_id for m in aside]


def test_single_nonspecific_symptom_gives_no_prediction():
    ids, _, _ = cands({"fatigue": "present"})
    assert ids == []


def test_overlap_cold_vs_allergy_both_considered():
    ids, m, _ = cands({"sneezing": "present", "runny_nose": "present", "blocked_nose": "present"})
    assert {"common_cold", "allergic_rhinitis"} <= set(ids)


def test_contradictory_information_lowers_support():
    _, before, _ = cands({"sneezing": "present", "itchy_eyes": "present", "runny_nose": "present", "allergen_trigger": "present"})
    _, after, _ = cands({"sneezing": "present", "itchy_eyes": "present", "runny_nose": "present", "allergen_trigger": "present",
                         "fever": "present", "body_ache": "present"})
    order = ["stronger", "partial", "limited"]
    assert order.index(after["allergic_rhinitis"].level) > order.index(before["allergic_rhinitis"].level)


def test_long_duration_sets_cold_aside_not_ruled_out():
    ids, _, aside = cands({"sneezing": "present", "runny_nose": "present", "itchy_eyes": "present"}, {"duration_days": 30})
    assert "common_cold" not in ids and "common_cold" in aside
    assert "allergic_rhinitis" in ids


def test_flu_requires_fever():
    ids, _, _ = cands({"body_ache": "present", "fatigue": "present", "cough": "present"})
    assert "flu_like_illness" not in ids


def test_insufficient_for_out_of_scope_symptoms(engine):
    _, r = run_flow(engine, "en", ["back pain and dizziness"])
    a = r["assessment"]
    assert a["status"] == "insufficient" and a["conditions"] == []
    assert a["urgency"]["level"] in ("soon", "urgent")


def test_child_is_out_of_scope(engine):
    _, r = run_flow(engine, "en", ["runny nose and sneezing"], answers={"q_age": "child"})
    assert r["assessment"]["status"] == "age_out_of_scope"
    assert r["assessment"]["conditions"] == []


def test_no_percentages_or_medicine_doses_in_output(engine):
    _, r = run_flow(engine, "en", ["sudden fever, body ache, dry cough"])
    blob = re.sub(r"https?://\S+", "", json.dumps(r["assessment"]))  # URL-encoding (%20) is not a percentage
    assert not re.search(r"\d+\s?%", blob)
    assert not re.search(r"\d+\s?mg\b", blob, re.I)


def test_assessment_updates_when_answer_changes(engine):
    st, r = run_flow(engine, "en", ["sneezing, runny nose, itchy eyes"])
    before = [c["id"] for c in r["assessment"]["conditions"]]
    r = engine.edit_symptom(st, "fever", "present")
    r = engine.edit_symptom(st, "body_ache", "present")
    after = {c["id"]: c["support"]["level"] for c in r["assessment"]["conditions"]}
    assert r["stage"] == "assessment"
    assert "flu_like_illness" in after or after.get("allergic_rhinitis") != "stronger"
    assert before != list(after) or after.get("allergic_rhinitis") != "stronger"


def test_vague_complaint_flow(engine):
    st, r = engine.start("hi")
    r = engine.message(st, "mujhe infection ho raha hai")
    assert r["question"]["id"] == "clarify_general"
    assert not any(m["kind"] == "unrecognised" for m in r["messages"])
    r = engine.answer(st, "clarify_general", ["fever", "sore_throat"])
    assert {"fever", "sore_throat"} <= st.present()
    assert r["question"]["kind"] == "screen"          # normal flow continues with the safety check
