# Explainable Bilingual Medical Chatbot

A Hinglish (Hindi + English) medical chatbot that provides symptom-based disease guidance using a knowledge graph built from WHO fact sheets. Powered by Groq LLM with an interactive D3.js knowledge graph visualization.

---

## Features

- **Bilingual chat** — responds in natural Hinglish (Hindi + English mix)
- **Symptom-based retrieval** — matches user symptoms to diseases via a keyword-indexed knowledge graph
- **Explainable reasoning** — tells users *why* a disease is suspected, not just what it is
- **Emergency triage** — bypasses LLM for critical keywords (chest pain, seizure, etc.) and routes to emergency services immediately
- **Knowledge graph visualization** — interactive D3.js force-directed graph of 76 diseases and their symptom connections
- **WHO-sourced data** — all disease facts scraped from official WHO fact sheets and structured by LLM

---

## Project Structure

```
project_out/
├── app.py                  # Flask web server and API routes
├── chatbot.py              # Groq LLM client, system prompt, message builder
├── knowledge_graph.py      # DiseaseKnowledgeGraph — loads JSON, indexes symptoms, retrieves context
├── fetch_datasets.py       # One-time scraper: fetches 73 diseases from WHO → dataset_OUR/
├── refetch.py              # Re-fetches 21 sparse/old disease files with better WHO content
├── refetch2.py             # Re-fetches 11 remaining empty disease files
├── requirements.txt        # Python dependencies
├── .env                    # API keys (not committed)
├── dataset_OUR/            # 76 WHO-sourced disease JSON files
└── templates/
    ├── index.html          # Chat UI (Hinglish, suggestion chips, emergency banner)
    └── graph.html          # D3.js knowledge graph visualization
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
pip install beautifulsoup4 requests  # needed for fetch scripts
```

### 2. Configure environment

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_groq_api_key_here
```

Get a free key at [console.groq.com](https://console.groq.com).

### 3. Run the app

```bash
python app.py
```

Open `http://127.0.0.1:5000` in your browser.

---

## How It Works

### Chat Flow

```
User message
    │
    ├─ is_emergency() ──► Hardcoded emergency response (112/108)
    │
    └─ DiseaseKnowledgeGraph.retrieve()
            │  keyword match + disease name match
            └─ Top 3–4 relevant diseases
                    │
                    └─ Injected into user turn as [KNOWLEDGE BASE]
                            │
                            └─ Groq LLM (llama-3.3-70b-versatile)
                                    │
                                    └─ Hinglish response with reasoning
```

### Knowledge Graph

- **76 diseases** from WHO fact sheets
- **42 symptom keywords** (English + Hinglish)
- Each disease is linked to symptom nodes it mentions across all fields (symptoms, diagnosis, treatment, transmission, prevention, overview)
- Retrieval uses keyword scoring — diseases with more symptom matches rank higher

### Model Fallback Chain

The app tries models in order, falling back on rate limits:
1. `llama-3.3-70b-versatile` — primary (best quality)
2. `llama-3.1-8b-instant` — fallback
3. `gemma2-9b-it` — last resort

---

## API Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/` | GET | Chat UI |
| `/chat` | POST | Send message, get LLM reply |
| `/reset` | POST | Clear conversation history |
| `/graph` | GET | Knowledge graph visualization |
| `/kg-info` | GET | `{"count": 76}` — number of loaded diseases |
| `/kg-data` | GET | Graph nodes and links for D3.js |

### `/chat` Request/Response

```json
// Request
{ "message": "mujhe bukhar aur sar dard hai" }

// Response
{ "reply": "Samajh sakta hoon...", "emergency": false }
```

---

## Dataset

76 JSON files in `dataset_OUR/`, each structured as:

```json
{
  "disease": "Dengue",
  "source": "World Health Organization (WHO) – Fact Sheet",
  "overview": "...",
  "symptoms": ["high fever", "severe headache", "pain behind eyes", ...],
  "diagnosis": ["NS1 antigen test", "PCR", ...],
  "treatment": ["fluid replacement", "paracetamol", ...],
  "transmission": ["Aedes mosquito bite"],
  "prevention": ["mosquito repellent", "eliminate standing water", ...],
  "risk_factors": ["tropical climate", "urban areas", ...],
  "complications": ["dengue haemorrhagic fever", "dengue shock syndrome"],
  "key_facts": ["400 million infections per year", ...]
}
```

To rebuild the dataset from scratch:

```bash
python fetch_datasets.py   # fetches all 73+ diseases
python refetch.py          # re-fetches sparse entries
python refetch2.py         # re-fetches remaining empty entries
```

---

## Safety Disclaimers

- This chatbot is for **informational purposes only** and does not provide medical diagnosis.
- All responses end with a recommendation to consult a doctor.
- Emergency symptoms trigger an immediate hardcoded response directing users to call 112 (India emergency) or 108 (ambulance).
- The LLM is explicitly instructed never to give definitive diagnoses — only possibilities.
