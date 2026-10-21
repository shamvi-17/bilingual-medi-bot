# MediBot — Explainable Bilingual Symptom Guide

A prototype symptom-assessment assistant for Indian users that talks in **Hinglish** (Roman-script Hindi + English) or **English**, screens for emergency warning signs first, asks only the follow-up questions that change the picture, and explains which common, lower-risk conditions fit — with a verifiable source passage behind every medical statement.

> **Not a diagnostic device.** It compares answers with public patient-information pages (NHS, MedlinePlus, WHO). The rules have **not** been reviewed by a clinician, and the evaluation in `evaluation/` is a software test, not a clinical validation.

---

## Quick start

```bash
pip install -r requirements-dev.txt
```

```bash
cp .env.example .env    # optional: add GROQ_API_KEY
```

```bash
python app.py
```

Open http://localhost:5001. Optional multilingual dense retrieval (otherwise BM25 only):

```bash
pip install -r requirements-ml.txt
```

Run the tests and the scenario evaluation:

```bash
python -m pytest -q
```

```bash
python -m evaluation.run_eval
```

The app works **without** a Groq key: rule-based extraction, red-flag screening, matching, retrieval and explanations are all local. The key only enables (a) understanding wording the rules don't recognise, (b) an optional plain-language rephrasing of the assessment, and (c) voice input.

---

## How an assessment works

```
user text / answer
   │
   ├─ extraction.py     English + Hinglish lexicon → canonical symptoms (present / absent / unsure),
   │                    user's own words, duration, onset, progression, severity hints; ambiguous words
   │                    ("dard", "cold", "weakness") trigger a clarification question instead of a guess
   │                    └─ llm.py (optional) maps unrecognised wording onto the SAME vocabulary; output is
   │                       rejected unless ids exist and the quoted words are really in the message
   ├─ redflags.py       runs on every turn, before anything else; emergency → routine assessment stops
   │                    and 112 / 108 (or Tele-MANAS 14416) guidance is shown with the cited reason
   ├─ followup.py       safety screen for the body areas involved → age, duration → discriminating
   │                    checklists chosen by how much they separate the remaining candidates → a few
   │                    context questions only when relevant. Nothing already answered is asked again.
   ├─ matcher.py        explicit counting rules over source-derived symptom–condition associations;
   │                    qualitative levels only (no percentages); conditions with too much against them
   │                    are "set aside", never "ruled out"; no candidate → "insufficient", no guess
   ├─ retrieval.py      hybrid BM25 + multilingual MiniLM embeddings over the ingested corpus, with
   │                    topic filters, source priority and a relevance check
   ├─ explain.py        per-condition explanation: what fits (user's words + source quote), what fits
   │                    less well, what's unknown, alternatives, what would help, self-care, when to see
   │                    a doctor, urgency with reasons — every claim resolved to a verbatim passage
   └─ engine.py / state.py   orchestration + structured state persisted in SQLite between requests
```

The language model never decides likelihoods or conditions. It is optional and its output is validated.

### Scope

Common cold, flu-like illness, allergic rhinitis, sinusitis, sore throat, indigestion/acid reflux, constipation, tension-type headache, migraine, contact dermatitis, hives, heat rash. Symptoms outside this scope are recorded and the user is told the tool can't assess them. Children under 12 are out of scope (no condition suggestions; advice to see a doctor). Red-flag screening covers chest pain, severe breathing difficulty, stroke signs, sudden severe headache, meningitis signs, anaphylaxis, inability to swallow, severe bleeding / vomiting blood, black stool, severe abdominal pain, dengue warning signs, seizures, confusion/fainting and self-harm, plus "get help today" rules (e.g. blood in stool, headache with vomiting).

No medicines or doses are recommended; self-care is limited to non-drug measures from the sources, and medicine questions are directed to a pharmacist or doctor.

---

## Project structure

```
app.py                      Flask app: UI, /api blueprint, legacy /chat, /transcribe, knowledge-graph pages
medassist/
  config.py                 environment-driven settings
  extraction.py             symptom extraction (EN / Hinglish), negation, uncertainty, duration
  redflags.py               red-flag screening layer
  followup.py               adaptive question selection + answer application
  matcher.py                conservative condition matching
  retrieval.py              hybrid retrieval (BM25 + optional embeddings)
  explain.py                explanation engine + urgency + citation validation
  llm.py                    optional Groq helpers with output validation
  engine.py, state.py       orchestration and persisted state
  api.py                    JSON API with validated request models
  data/                     reviewable rule data: symptoms.json, redflags.json, conditions.json, questions.json
  knowledge/                sources.json, ingest.py, corpus.jsonl, manifest.json, verify_live.py
templates/index.html        landing page + assessment workspace
static/css/app.css, static/js/app.js
tests/                      pytest suite (147 tests)
evaluation/                 scenario dataset, runner, results.md
docs/KNOWLEDGE_BASE.md      sources, ingestion, licensing, known gaps
dataset_OUR/, knowledge_graph.py, chatbot.py, templates/graph.html, fetch_datasets.py, refetch*.py
                            original WHO fact-sheet dataset and D3 knowledge-graph explorer (kept)
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/assessments` | start (`{"language": "hi"\|"en"}`) |
| GET | `/api/assessments/{id}` | current state + transcript |
| POST | `/api/assessments/{id}/messages` | free-text symptoms (`{"text": ...}`) |
| POST | `/api/assessments/{id}/answers` | answer a follow-up (`{"question_id", "value"}`) |
| POST | `/api/assessments/{id}/symptoms` | add structured symptoms |
| PATCH / DELETE | `/api/assessments/{id}/symptoms/{symptom}` | correct (`present`/`absent`/`unsure`) or remove |
| PATCH | `/api/assessments/{id}/attributes` | edit duration, severity, onset, progression, age group |
| PATCH | `/api/assessments/{id}/language` | switch language, keeping all answers |
| POST | `/api/assessments/{id}/red-flags/{flag}/dismiss` | "this doesn't apply to me" |
| POST | `/api/assessments/{id}/assessment` | produce the assessment now |
| GET | `/api/assessments/{id}/summary` | optional LLM plain-language rephrasing (validated) |
| POST | `/api/assessments/{id}/reset` | start over |
| GET | `/api/evidence?q=&condition=` | search the evidence corpus |
| GET | `/api/sources`, `/api/sources/{id}` | source metadata, review dates, passages |
| GET | `/api/health`, `/api/meta` | corpus / retrieval / LLM status; symptom & condition vocabulary |

Every response for an assessment has the same shape: `stage`, `progress`, new `messages`, at most one `question`, `emergency` or `assessment`, plus the editable `symptoms` and `attributes`. Errors are `{"error": {"code", "message", "details"}}`.

## Knowledge base

`python -m medassist.knowledge.ingest` fetches the 40 pages in `medassist/knowledge/sources.json` (NHS, MedlinePlus, WHO), extracts the main text, and stores 374 section-aware chunks verbatim with publisher, URL, last-reviewed date and retrieval date. `python -m medassist.knowledge.verify_live` checks every quote the rules cite against the live pages. See [docs/KNOWLEDGE_BASE.md](docs/KNOWLEDGE_BASE.md) for licensing and the documented gaps (no India-specific MoHFW/NHP pages yet; CDC blocks automated access).

## Original WHO knowledge graph

The original 76-disease WHO dataset and the D3 explorer are still available at `/graph`. Those JSON files were structured by an LLM from WHO fact sheets and contain no source URLs or verbatim text, so they are **not** used as evidence in assessments.

## Deployment (Render)

`render.yaml` deploys with gunicorn, BM25-only retrieval (torch is too heavy for the free plan) and a generated `SECRET_KEY`. Set `GROQ_API_KEY` in the dashboard if wanted. The free plan's disk is ephemeral, so saved assessments don't survive redeploys.
