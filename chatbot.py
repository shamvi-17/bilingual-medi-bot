from groq import Groq
from knowledge_graph import DiseaseKnowledgeGraph
from dotenv import load_dotenv
import os

load_dotenv()

kg = DiseaseKnowledgeGraph(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dataset_OUR"))
# Created lazily so the app still starts (with LLM features disabled) when GROQ_API_KEY is missing.
_client = None


def get_client() -> Groq:
    global _client
    if _client is None:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")
        _client = Groq(api_key=key)
    return _client

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
    # the original llama/gemma models were decommissioned by Groq; models now come from LLM_MODELS
    models = [m.strip() for m in os.environ.get("LLM_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b").split(",") if m.strip()]
    for model in models:
        try:
            response = get_client().chat.completions.create(
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

def is_emergency(text: str) -> bool:
    """Quick rule-based triage before hitting the LLM."""
    RED_FLAGS = [
        "chest pain", "seene mein dard", "can't breathe", "saans nahi",
        "unconscious", "hosh nahi", "seizure", "stroke", "bahut zyada khoon",
        "heavy bleeding", "suicide", "khud ko hurt"
    ]
    text_lower = text.lower()
    return any(flag in text_lower for flag in RED_FLAGS)