from flask import Flask, request, jsonify, render_template, session
from chatbot import kg
from medassist import voice
from medassist.api import bp as api_bp, store
from medassist.engine import get_engine
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
# A fixed SECRET_KEY keeps sessions valid across gunicorn workers/restarts; random is fine for local dev.
app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)
app.config["JSON_SORT_KEYS"] = False
app.register_blueprint(api_bp)


def _warm_up():
    """Load the corpus and embedding index in the background so the first assessment isn't slow."""
    try:
        from medassist.retrieval import get_retriever
        get_retriever()
    except Exception:
        app.logger.exception("Retriever warm-up failed; retrieval will fall back on first use")


if os.environ.get("MEDASSIST_WARMUP", "1") == "1":
    import threading
    threading.Thread(target=_warm_up, daemon=True).start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    """Legacy text-only endpoint, now backed by the structured assessment engine."""
    data = request.get_json(silent=True) or {}
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400
    engine = get_engine()
    st = store().get(session.get("assessment_id", "")) if session.get("assessment_id") else None
    if st is None:
        st, _ = engine.start(data.get("language", "hi"))
        session["assessment_id"] = st.id
    resp = engine.message(st, user_message)
    store().save(st)
    parts = [m["text"] for m in resp["messages"]]
    if resp["emergency"]:
        e = resp["emergency"]
        parts = [e["title"], e["instruction"]]
    elif resp["question"]:
        q = resp["question"]
        parts.append(q["text"] + (" (" + " / ".join(o["label"] for o in q["options"]) + ")" if q["options"] else ""))
    elif resp["assessment"]:
        parts.append(resp["assessment"]["summary"])
    return jsonify({"reply": "\n".join(p for p in parts if p), "emergency": bool(resp["emergency"]),
                    "assessment_id": st.id})


@app.route("/transcribe", methods=["POST"])
def transcribe():
    """Legacy endpoint; the UI uses /api/voice/transcribe."""
    audio = request.files.get("audio")
    if not audio:
        return jsonify({"error": "No audio file"}), 400
    try:
        res = voice.transcribe(audio.read(), audio.filename or "audio.webm")
    except voice.VoiceError as e:
        return jsonify({"error": str(e)}), 503 if e.code in ("unavailable", "provider_error") else 422
    if not res.accepted:
        return jsonify({"error": "Could not recognise speech reliably. Please try again or type."}), 422
    return jsonify({"transcript": res.text})


@app.route("/reset", methods=["POST"])
def reset():
    session.pop("assessment_id", None)
    return jsonify({"status": "ok"})

@app.route("/kg-info")
def kg_info():
    return jsonify({"count": len(kg.graph)})

@app.route("/graph")
def graph():
    return render_template("graph.html")

@app.route("/kg-data")
def kg_data():
    KEYWORDS = [
        "fever", "headache", "cough", "fatigue", "rash", "pain", "nausea",
        "vomiting", "diarrhoea", "diarrhea", "bleeding", "swelling",
        "breathless", "seizure", "jaundice", "confusion", "weakness",
        "itching", "discharge", "chills", "sweating", "chest pain",
        "sore throat", "body ache", "joint pain", "muscle pain",
        "numbness", "ulcer", "skin lesion", "weight loss", "anaemia",
        "paralysis", "blindness", "dehydration", "inflammation",
        "infection", "cancer", "tumor", "anxiety", "depression",
        "cognitive", "memory loss", "tremor", "liver", "kidney",
    ]

    nodes, links = [], []
    seen_symptoms = set()

    for disease_key, info in kg.graph.items():
        d_id = "d__" + disease_key
        nodes.append({"id": d_id, "label": info["name"], "type": "disease"})

        # Build full text from ALL fields for richer matching
        all_parts = (
            info["symptoms"] + info["diagnosis"] +
            info["treatment"] + info["transmission"] +
            info["prevention"] + [info["overview"]]
        )
        full_text = " ".join(all_parts).lower()

        for kw in KEYWORDS:
            if kw in full_text:
                s_id = "s__" + kw
                if s_id not in seen_symptoms:
                    nodes.append({"id": s_id, "label": kw, "type": "symptom"})
                    seen_symptoms.add(s_id)
                links.append({"source": d_id, "target": s_id})

    return jsonify({"nodes": nodes, "links": links})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
