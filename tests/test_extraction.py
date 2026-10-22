import pytest

from medassist.extraction import detect_language, extract, parse_duration, parse_yes_no


def found(text):
    return {f.symptom: f.status for f in extract(text).findings}


@pytest.mark.parametrize("text,expected", [
    ("I have a runny nose and sneezing", {"runny_nose": "present", "sneezing": "present"}),
    ("sore throat and a hoarse voice", {"sore_throat": "present", "hoarse_voice": "present"}),
    ("burning in my chest after eating and a sour taste", {"heartburn": "present", "sour_regurgitation": "present", "worse_after_eating": "present"}),
    ("I haven't pooped in 4 days and my stools are hard", {"infrequent_stools": "present", "hard_stools": "present"}),
    ("itchy rash with raised bumps", {"skin_itch": "present", "skin_rash": "present", "raised_welts": "present"}),
    ("my head hurts on one side and it is throbbing", {"headache": "present", "headache_one_side": "present", "headache_throbbing": "present"}),
])
def test_english_extraction(text, expected):
    got = found(text)
    for k, v in expected.items():
        assert got.get(k) == v, (text, got)


@pytest.mark.parametrize("text,expected", [
    ("mera naak band hai aur throat mein mucus aa raha hai", {"blocked_nose": "present", "postnasal_drip": "present"}),
    ("2 din se bukhar hai aur badan dard", {"fever": "present", "body_ache": "present"}),
    ("khaane ke baad seene mein jalan aur khatti dakar", {"heartburn": "present", "sour_regurgitation": "present"}),
    ("pet saaf nahi ho raha, potty bahut sakht hai", {"infrequent_stools": "present", "hard_stools": "present"}),
    ("sar ke ek taraf dhak dhak dard", {"headache": "present", "headache_one_side": "present", "headache_throbbing": "present"}),
    ("ghamoriyan ho gayi garmi mein", {"small_raised_spots": "present", "heat_sweat_trigger": "present"}),
    ("aankh mein khujli aur chheenk", {"itchy_eyes": "present", "sneezing": "present"}),
])
def test_hinglish_extraction(text, expected):
    got = found(text)
    for k, v in expected.items():
        assert got.get(k) == v, (text, got)


def test_longest_match_prevents_misattribution():
    # "aankh mein khujli" must not be read as itchy skin
    got = found("aankh mein khujli")
    assert "itchy_eyes" in got and "skin_itch" not in got


@pytest.mark.parametrize("text", ["bukharrr hai", "bukhaar hai", "bukhar hai", "fever hai", "tez bukhar"])
def test_spelling_variants(text):
    assert found(text).get("fever") == "present"


@pytest.mark.parametrize("text,sym", [
    ("khansi nahi hai", "cough"),
    ("no fever", "fever"),
    ("I don't have a cough", "cough"),
    ("bukhar bilkul nahi", "fever"),
])
def test_negation(text, sym):
    assert found(text)[sym] == "absent"


def test_negation_scope_list_and_clause():
    got = found("runny nose, no fever or cough")
    assert got["runny_nose"] == "present"
    assert got["fever"] == "absent" and got["cough"] == "absent"
    got = found("sar dard hai lekin bukhar nahi")
    assert got["headache"] == "present" and got["fever"] == "absent"


def test_unsure_not_read_as_negation():
    # "pata nahi" contains "nahi" but means "not sure"
    assert found("pata nahi bukhar hai ya nahi")["fever"] == "unsure"


def test_correction_within_message_latest_wins():
    assert found("fever hai... actually fever nahi hai")["fever"] == "absent"


def test_blocked_nose_breathing_is_not_breathlessness():
    got = found("I can't breathe through my nose")
    assert got.get("blocked_nose") == "present" and "breathlessness" not in got
    assert found("naak se saans nahi aa rahi").get("blocked_nose") == "present"


@pytest.mark.parametrize("text,days", [
    ("3 din se", 3), ("since yesterday", 1), ("kal se", 1), ("2 weeks", 14), ("ek hafte se", 7), ("parso se", 2), ("6 hours", 0.25),
])
def test_duration(text, days):
    assert parse_duration(text) == pytest.approx(days)


@pytest.mark.parametrize("text,q", [("mujhe dard hai", "clarify_pain_location"), ("I have a cold", "clarify_cold"), ("weakness", "clarify_weakness")])
def test_ambiguous_terms_trigger_clarification(text, q):
    assert q in extract(text).clarifications


def test_specific_pain_does_not_need_clarification():
    assert not extract("pet mein dard").clarifications
    assert not extract("sar ke ek taraf dard").clarifications


def test_preserves_user_words():
    f = [x for x in extract("mera naak band hai").findings if x.symptom == "blocked_nose"][0]
    assert f.words == "naak band"


def test_language_detection_and_yes_no():
    assert detect_language("mujhe 2 din se bukhar hai") == "hi"
    assert detect_language("I have had a fever for two days") == "en"
    assert parse_yes_no("haan") == "yes" and parse_yes_no("nahi") == "no"
    assert parse_yes_no("pata nahi") == "unsure" and parse_yes_no("yes it does") == "yes"


# Phrasings collected *after* the lexicon was written (an informal held-out probe). Two of these were
# previously misattributed ("pet" = stomach read as pets; throat "chubhna" read as prickly rash).
@pytest.mark.parametrize("text,sym,not_sym", [
    ("pet mein gas ban rahi hai", "bloating", "allergen_trigger"),
    ("gala chhil gaya hai, nigalte hi chubhta hai", "sore_throat", "small_raised_spots"),
    ("nose is stuffed up", "blocked_nose", None),
    ("teen din se latrine nahi gaya", "infrequent_stools", None),
    ("my tummy feels heavy and I'm gassy", "bloating", None),
    ("jukham ho gaya hai", "runny_nose", None),
    ("chest feels heavy when I walk", "chest_pain", None),
    ("motion bahut patla aa raha hai", "diarrhoea", "infrequent_stools"),
    ("sar chakra raha hai", "dizziness", None),
    ("sar bhari rehta hai", "headache", None),
    ("I keep clearing my throat", "postnasal_drip", None),
    ("my pet dog makes me sneeze", "allergen_trigger", None),
])
def test_unseen_phrasings(text, sym, not_sym):
    got = found(text)
    assert got.get(sym) == "present", got
    if not_sym:
        assert not_sym not in got, got
