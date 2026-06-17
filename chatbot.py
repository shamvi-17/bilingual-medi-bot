from groq import Groq
from knowledge_graph import DiseaseKnowledgeGraph
from dotenv import load_dotenv
import os

load_dotenv()

kg = DiseaseKnowledgeGraph("dataset_OUR/")
client = Groq(api_key=os.environ["GROQ_API_KEY"])

SYSTEM_PROMPT = """You are a trusted, empathetic medical assistant.

## LANGUAGE RULE (HIGHEST PRIORITY):
Detect the language of the user's LATEST message and match it exactly:
- If the message is in **English** → reply fully in English
- If the message is **Hinglish** (Hindi + English mix, or Hindi words in Roman script) → reply in Hinglish
- Never switch languages mid-conversation unless the user does first

## Response Style (STRICT):
- SHORT and CRISP — max 3-4 lines per response
- Bullet points over paragraphs
- ONLY ONE follow-up question per response — never ask two at once
- Warm tone, but to the point

## Symptom-Gathering Workflow:

**Until 3+ clear symptoms are known:**
1. Acknowledge the symptom in 1 line
2. Ask EXACTLY ONE targeted follow-up question to narrow the diagnosis

**Once 3+ symptoms are clear or a pattern is obvious:**
- 2-3 bullet points: possible disease with short reasoning
- Suggest 1 relevant test
- End with a doctor referral (1 line)

**Good discriminating questions (ask only one per turn):**
- English: "How many days have you had the fever?" / "Where exactly is the rash?" / "Did the symptoms come on suddenly?"
- Hinglish: "Bukhar kitne din se hai?" / "Rash kahan hai?" / "Symptoms achanak aaye ya dheere dheere?"

## HARD RULES:
- ONE question per response — never break this
- Never give a definitive diagnosis — use "could be" / "ho sakta hai"
- Serious symptoms (chest pain, difficulty breathing) → refer to emergency immediately, skip questions
- Not in knowledge base → say "Please consult a doctor" / "Doctor se poochein"
- Max 2 diseases per response
"""

def build_messages(user_message: str, history: list[dict]) -> list[dict]:
    # Build a combined symptom query from full conversation so KG retrieval
    # captures diseases even when symptoms are spread across multiple turns.
    prior_user_text = " ".join(
        m["content"] for m in history if m["role"] == "user"
    )
    combined_query = f"{prior_user_text} {user_message}".strip()

    diseases = kg.retrieve(combined_query)
    kg_context = kg.format_context(diseases)

    # Inject KG into current user turn only (not history)
    grounded_user_turn = f"""{user_message}

[KNOWLEDGE BASE - Use these facts to ground your answer]
{kg_context}
[END KNOWLEDGE BASE]"""

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": grounded_user_turn})
    return messages

def get_reply(user_message: str, history: list[dict]) -> str:
    messages = build_messages(user_message, history)
    for model in ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "gemma2-9b-it"]:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=300,
                temperature=0.4,
            )
            return response.choices[0].message.content
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                continue
            raise
    return "Abhi server busy hai — thodi der baad try karein. (Rate limit reached, please try again in a few minutes.)"

def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.webm",
    language: str | None = None,
    context: str = "",
) -> str:
    """Transcribe audio via Groq Whisper — handles Hindi, English, and Hinglish."""
    # Prompt seeds Whisper with domain vocabulary so it spells medical Hinglish correctly.
    # If the last bot message is passed as context it also primes the transcription window.
    vocab = (
        "bukhar, dard, khansi, sar dard, thakan, rash, ulti, nausea, pet dard, "
        "saans, kamzori, khujli, sujan, chakkad, diabetes, dengue, malaria, TB."
    )
    prompt = f"{context} {vocab}".strip() if context else vocab

    kwargs = dict(
        file=(filename, audio_bytes),
        model="whisper-large-v3",        # full model — highest accuracy
        response_format="text",
        temperature=0,                   # deterministic output
        prompt=prompt,
    )
    if language:                         # hi / en — skip for auto-detect
        kwargs["language"] = language

    transcription = client.audio.transcriptions.create(**kwargs)
    return transcription.strip() if isinstance(transcription, str) else transcription

def is_emergency(text: str) -> bool:
    """Quick rule-based triage before hitting the LLM."""
    RED_FLAGS = [
        "chest pain", "seene mein dard", "can't breathe", "saans nahi",
        "unconscious", "hosh nahi", "seizure", "stroke", "bahut zyada khoon",
        "heavy bleeding", "suicide", "khud ko hurt"
    ]
    text_lower = text.lower()
    return any(flag in text_lower for flag in RED_FLAGS)