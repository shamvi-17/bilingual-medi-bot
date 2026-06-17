from flask import Flask, request, jsonify, render_template, session
from chatbot import get_reply, is_emergency, kg, transcribe_audio
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route("/")
def index():
    session["history"] = []
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = data.get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    # Emergency triage — bypass LLM for speed
    if is_emergency(user_message):
        reply = (
            "Yeh symptoms serious lag rahe hain. "
            "Please ABHI emergency services call karein ya nearest hospital jaayein. "
            "India mein: 112 (emergency) | 108 (ambulance)"
        )
        return jsonify({"reply": reply, "emergency": True})

    # Get or init conversation history
    history = session.get("history", [])

    # Get LLM reply
    try:
        reply = get_reply(user_message, history)
    except Exception as e:
        return jsonify({"reply": "Server abhi busy hai. Thodi der baad try karein. (Service temporarily unavailable)", "emergency": False}), 200

    # Update session history (keep last 10 turns to manage token cost)
    history.append({"role": "user", "content": user_message})
    history.append({"role": "assistant", "content": reply})
    session["history"] = history[-20:]  # last 10 turns = 20 messages

    return jsonify({"reply": reply, "emergency": False})

@app.route("/transcribe", methods=["POST"])
def transcribe():
    audio    = request.files.get("audio")
    language = request.form.get("language") or None   # "hi" | "en" | None (auto)
    context  = request.form.get("context", "")        # last bot message for priming
    if not audio:
        return jsonify({"error": "No audio file"}), 400
    try:
        transcript = transcribe_audio(audio.read(), audio.filename or "audio.webm", language, context)
        return jsonify({"transcript": transcript})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/reset", methods=["POST"])
def reset():
    session["history"] = []
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
    app.run(host="0.0.0.0", port=port, debug=True)