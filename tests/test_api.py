import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def start(client, lang="en"):
    r = client.post("/api/assessments", json={"language": lang})
    assert r.status_code == 201
    return r.json["session_id"], r.json


def answer_all(client, sid, r):
    for _ in range(20):
        q = r["question"]
        if not q:
            return r
        v = "none" if q["type"] == "multi" else 3 if q["type"] == "scale" else "no" if q["type"] == "yesno" else \
            {"q_age": "adult", "q_duration": "1to3"}.get(q["id"], q["options"][-1]["value"])
        r = client.post(f"/api/assessments/{sid}/answers", json={"question_id": q["id"], "value": v}).json
    return r


def test_full_flow_and_state_persists_between_requests(client):
    sid, r = start(client, "hi")
    assert r["stage"] == "symptoms" and r["messages"]
    r = client.post(f"/api/assessments/{sid}/messages", json={"text": "naak band hai aur chheenk aa rahi hai"}).json
    assert r["stage"] == "safety"
    # state survives a separate GET
    g = client.get(f"/api/assessments/{sid}").json
    assert {s["id"] for s in g["symptoms"]} >= {"blocked_nose", "sneezing"}
    assert g["transcript"][1]["text"].startswith("naak band")
    r = answer_all(client, sid, r)
    assert r["stage"] == "assessment"
    assert r["assessment"]["conditions"]


def test_language_switch_preserves_state(client):
    sid, _ = start(client, "en")
    client.post(f"/api/assessments/{sid}/messages", json={"text": "sore throat and cough since 2 days"})
    r = client.patch(f"/api/assessments/{sid}/language", json={"language": "hi"}).json
    assert r["language"] == "hi"
    assert {s["id"] for s in r["symptoms"]} >= {"sore_throat", "cough"}
    assert r["attributes"]["duration_days"] == 2
    assert r["question"]["text"] != ""
    # the same pending question is re-rendered in Hinglish
    assert "kya" in r["question"]["text"].lower() or "safety" in r["question"]["text"].lower()


def test_correction_updates_assessment(client):
    sid, r = start(client)
    r = client.post(f"/api/assessments/{sid}/messages", json={"text": "sneezing, itchy eyes and runny nose"}).json
    r = answer_all(client, sid, r)
    levels = {c["id"]: c["support"]["level"] for c in r["assessment"]["conditions"]}
    r2 = client.patch(f"/api/assessments/{sid}/symptoms/fever", json={"status": "present"}).json
    levels2 = {c["id"]: c["support"]["level"] for c in r2["assessment"]["conditions"]}
    assert levels != levels2
    r3 = client.delete(f"/api/assessments/{sid}/symptoms/fever").json
    assert "fever" not in {s["id"] for s in r3["symptoms"]}


def test_attribute_edit_and_bulk_symptoms(client):
    sid, _ = start(client)
    r = client.post(f"/api/assessments/{sid}/symptoms", json={"symptoms": [{"id": "heartburn"}, {"id": "bloating"}]}).json
    assert {s["id"] for s in r["symptoms"]} == {"heartburn", "bloating"}
    r = client.patch(f"/api/assessments/{sid}/attributes", json={"name": "duration_days", "value": "21"}).json
    assert r["attributes"]["duration_days"] == 21


def test_force_assessment_and_reset(client):
    sid, _ = start(client)
    assert client.post(f"/api/assessments/{sid}/assessment").status_code == 409
    client.post(f"/api/assessments/{sid}/messages", json={"text": "constipation and hard stools"})
    r = client.post(f"/api/assessments/{sid}/assessment").json
    assert r["stage"] == "assessment"
    r = client.post(f"/api/assessments/{sid}/reset")
    assert r.status_code == 201 and r.json["session_id"] != sid
    assert client.get(f"/api/assessments/{sid}").status_code == 404


@pytest.mark.parametrize("method,path,body,code", [
    ("post", "/api/assessments", {"language": "fr"}, 422),
    ("post", "/api/assessments/{sid}/messages", {}, 422),
    ("post", "/api/assessments/{sid}/messages", {"text": ""}, 422),
    ("post", "/api/assessments/{sid}/answers", {"question_id": "nope", "value": "x"}, 400),
    ("patch", "/api/assessments/{sid}/symptoms/not_a_symptom", {"status": "present"}, 400),
    ("patch", "/api/assessments/{sid}/symptoms/fever", {"status": "maybe"}, 422),
    ("patch", "/api/assessments/{sid}/attributes", {"name": "secret", "value": 1}, 400),
    ("get", "/api/assessments/doesnotexist", None, 404),
    ("get", "/api/sources/nope", None, 404),
    ("get", "/api/evidence", None, 422),
])
def test_api_errors_are_structured(client, method, path, body, code):
    sid, _ = start(client)
    r = getattr(client, method)(path.format(sid=sid), json=body) if body is not None else getattr(client, method)(path.format(sid=sid))
    assert r.status_code == code
    assert "error" in r.json and r.json["error"]["message"]


def test_sources_and_evidence_endpoints(client):
    s = client.get("/api/sources").json["sources"]
    assert len(s) >= 30 and all(x["url"].startswith("https://") for x in s)
    d = client.get("/api/sources/nhs-common-cold").json
    assert d["publisher"] == "NHS" and d["passages"]
    e = client.get("/api/evidence?q=itchy+watery+eyes+sneezing&condition=allergic_rhinitis").json
    assert e["results"] and e["results"][0]["source_id"].startswith(("nhs-allergic", "nhs-hay", "mlp"))
    h = client.get("/api/health").json
    assert h["corpus"]["chunks"] > 300


def test_llm_unavailable_flow_still_works(client):
    # conftest disables the LLM provider; the summary endpoint must degrade, not fail
    sid, r = start(client)
    r = client.post(f"/api/assessments/{sid}/messages", json={"text": "blocked nose and sneezing"}).json
    answer_all(client, sid, r)
    s = client.get(f"/api/assessments/{sid}/summary")
    assert s.status_code == 200 and s.json["available"] is False


def test_unrecognised_text_handled_gracefully(client):
    sid, _ = start(client)
    r = client.post(f"/api/assessments/{sid}/messages", json={"text": "hello there how are you"}).json
    assert r["stage"] == "symptoms"
    assert any(m["kind"] == "unrecognised" for m in r["messages"])


def test_legacy_chat_endpoint(client):
    r = client.post("/chat", json={"message": "seene mein dard hai"})
    assert r.status_code == 200 and r.json["emergency"] is True
    assert client.post("/chat", json={"message": ""}).status_code == 400


# ── frontend ↔ backend integration ───────────────────────────────────────────

def test_index_serves_app_and_assets(client):
    html = client.get("/").data.decode()
    assert 'id="workspace"' in html and "js/app.js" in html and "css/app.css" in html
    assert client.get("/static/js/app.js").status_code == 200
    assert client.get("/static/css/app.css").status_code == 200


def test_frontend_calls_only_existing_api_routes(client):
    from app import app
    js = (ROOT / "static" / "js" / "app.js").read_text()
    used = set(re.findall(r"[`\"'](/api/[a-z\-/${}.A-Za-z_]*)", js))
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert used, "no API calls found in app.js"
    for path in used:
        pattern = re.sub(r"\$\{[^}]+\}", "<x>", path).rstrip("/")
        regex = "^" + re.sub(r"<x>", "[^/]+", re.escape(pattern).replace(re.escape("<x>"), "<x>")) + "$"
        assert any(re.match(regex, re.sub(r"<[^>]+>", "seg", rule)) for rule in rules), path


def test_frontend_has_no_hardcoded_predictions():
    js = (ROOT / "static" / "js" / "app.js").read_text().lower()
    for cond in ["allergic rhinitis", "tension-type headache", "contact dermatitis", "migraine is"]:
        assert cond not in js


def test_every_element_the_script_needs_exists_in_the_page(client):
    """The script and the page must agree on element ids (a mismatch broke the chat once)."""
    js = (ROOT / "static" / "js" / "app.js").read_text()
    html = client.get("/").data.decode()
    ids = set(re.findall(r'\$\("#([A-Za-z0-9_-]+)', js))
    # ids the script creates itself at runtime
    created = set(re.findall(r'\.id = "([A-Za-z0-9_-]+)"', js)) | set(re.findall(r'id="([A-Za-z0-9_-]+)"', js))
    missing = sorted(i for i in ids - created if f'id="{i}"' not in html)
    assert not missing, f"app.js looks up ids missing from index.html: {missing}"


def test_assets_are_versioned_and_page_not_cached(client):
    r = client.get("/")
    html = r.data.decode()
    assert r.headers.get("Cache-Control") == "no-cache"
    assert re.search(r'/static/js/app\.js\?v=\d+', html) and re.search(r'/static/css/app\.css\?v=\d+', html)
    from app import app
    assert app.config["TEMPLATES_AUTO_RELOAD"] is True


def test_dark_theme_blocks_match():
    """Dark tokens are declared twice (manual choice + system setting); they must stay identical."""
    css = (ROOT / "static" / "css" / "app.css").read_text()
    manual = re.search(r':root\[data-theme="dark"\] \{(.*?)\n\}', css, re.S).group(1)
    system = re.search(r':root:not\(\[data-theme="light"\]\) \{(.*?)\n  \}', css, re.S).group(1)
    norm = lambda block: sorted(" ".join(block.split()).split(";"))
    assert norm(manual) == norm(system)


def test_theme_toggle_present(client):
    html = client.get("/").data.decode()
    assert 'id="theme-btn"' in html and "medibot_theme" in html


def test_reopening_a_conversation_does_not_repeat_messages(client):
    sid, _ = start(client, "hi")
    client.post(f"/api/assessments/{sid}/messages", json={"text": "sar dard hai"})
    first = client.get(f"/api/assessments/{sid}").json["transcript"]
    again = client.get(f"/api/assessments/{sid}").json["transcript"]
    assert len(again) == len(first)
    texts = [m["text"] for m in again]
    assert all(a != b for a, b in zip(texts, texts[1:])), "a message was repeated back-to-back"
