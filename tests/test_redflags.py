import pytest

from medassist.redflags import get_rules
from conftest import run_flow


def ids(text, present=frozenset()):
    return {h.rule_id for h in get_rules().screen_text(text, set(present))}


@pytest.mark.parametrize("text,rule", [
    ("I have chest pain", "chest_pain"),
    ("seene mein dard ho raha hai", "chest_pain"),
    ("I can't breathe", "severe_breathing"),
    ("saans nahi aa rahi", "severe_breathing"),
    ("her face is drooping and speech is slurred", "stroke_signs"),
    ("chehra latak gaya aur bolne mein dikkat", "stroke_signs"),
    ("worst headache of my life", "thunderclap_headache"),
    ("achanak bahut tez sar dard", "thunderclap_headache"),
    ("my lips are swollen", "anaphylaxis"),
    ("hoth sooj gaye", "anaphylaxis"),
    ("I am vomiting blood", "severe_bleeding"),
    ("bleeding won't stop", "severe_bleeding"),
    ("he fainted", "confusion_drowsy"),
    ("had a seizure", "seizure"),
    ("I want to kill myself", "self_harm"),
    ("drooling and can't swallow", "cannot_swallow"),
])
def test_emergency_detection(text, rule):
    assert rule in ids(text)


@pytest.mark.parametrize("text", [
    "no chest pain", "seene mein dard nahi hai", "I can't breathe through my nose", "naak se saans nahi aa rahi",
    "I am confused about which medicine", "seene mein jalan", "sore throat and runny nose",
])
def test_no_false_alarm(text):
    assert not {r for r in ids(text) if get_rules().rules[r]["level"] == "emergency"}, text


def test_combination_rules_need_context():
    assert "stiff_neck_fever" not in ids("gardan akad gayi hai")
    assert "stiff_neck_fever" in ids("gardan akad gayi hai", {"fever"})
    assert "dengue_warning" in ids("masoodon se khoon", {"fever"})
    hits = {h.rule_id for h in get_rules().screen_state({"headache", "vomiting"})}
    assert "headache_vomiting" in hits


def test_red_flag_overrides_routine_assessment(engine):
    st, r = engine.start("en")
    r = engine.message(st, "runny nose and sneezing, and I have chest pain")
    assert r["stage"] == "emergency"
    assert r["question"] is None and r["assessment"] is None
    assert "112" in r["emergency"]["instruction"]
    assert r["emergency"]["reasons"][0]["citations"], "emergency reason must cite its source"


def test_emergency_from_screening_answer(engine):
    st, r = engine.start("hi")
    r = engine.message(st, "sar dard ho raha hai")
    assert r["question"]["id"] == "rf_head"
    r = engine.answer(st, "rf_head", ["sudden"])
    assert r["stage"] == "emergency"


def test_cross_message_combination(engine):
    st, r = engine.start("hi")
    engine.message(st, "gardan akad gayi hai")
    r = engine.message(st, "bukhar bhi hai")
    assert r["stage"] == "emergency"


def test_dismissed_flag_allows_continuing(engine):
    st, r = engine.start("en")
    r = engine.message(st, "chest pain and acidity after meals")
    assert r["stage"] == "emergency"
    r = engine.dismiss_flag(st, "chest_pain")
    assert r["stage"] != "emergency"
    # a dismissed flag is not re-raised by re-screening the same text
    r = engine.message(st, "burping too")
    assert r["stage"] != "emergency"


def test_urgent_flag_shown_but_assessment_continues(engine):
    st, r = run_flow(engine, "en", ["constipation, hard stools and blood in my stool"])
    assert r["stage"] == "assessment"
    assert r["assessment"]["urgency"]["level"] == "urgent"
    assert any(n["id"] == "blood_in_stool" for n in r["notices"])


def test_mental_health_contacts(engine):
    st, r = engine.start("en")
    r = engine.message(st, "I want to end my life")
    assert r["emergency"]["mental_health"] is True
    assert "14416" in r["emergency"]["instruction"]


def test_correcting_symptom_withdraws_its_text_flag_only(engine):
    st, r = engine.start("en")
    r = engine.message(st, "acidity after meals and chest pain")
    assert r["stage"] == "emergency"
    r = engine.edit_symptom(st, "chest_pain", "absent")
    assert r["stage"] != "emergency"
    # a flag raised by *different* words is not withdrawn by this correction
    st2, _ = engine.start("en")
    engine.message(st2, "chest pain going to my left arm")
    r = engine.edit_symptom(st2, "chest_pain", "absent")
    assert r["stage"] == "emergency"
    assert [x["id"] for x in r["emergency"]["reasons"]] == ["chest_pain_radiating"]
