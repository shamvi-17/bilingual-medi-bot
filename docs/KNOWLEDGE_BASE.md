# Knowledge base

## What is in it

`medassist/knowledge/sources.json` lists 41 public patient-information pages:

| Publisher | Pages | Used for |
|---|---|---|
| NHS (UK) | 32 | main symptom lists, self-care, "see a GP / call 999" safety-netting, red flags |
| MedlinePlus (U.S. National Library of Medicine) | 9 | descriptions and additional symptom lists |
| WHO | 3 | influenza, headache disorders, dengue warning signs |

`python -m medassist.knowledge.ingest` fetches each page, extracts the main article with a publisher-specific parser, removes navigation, image credits and page furniture, and splits the text into chunks that never cross a section heading (so a "Call 999 if" list is never merged with a self-care list). A list keeps its introducing sentence. Each chunk stores:

`chunk_id, source_id, title, publisher, url, section, text, topics, priority, last_reviewed, retrieved`

Text is stored verbatim (only whitespace and typographic quotes/dashes are normalised). Nothing is paraphrased by an LLM. `manifest.json` records per-source status, review dates (and NHS "next review due" dates) and failures.

## How evidence is used

* **Curated associations** (`medassist/data/*.json`): every symptom–condition link, contradiction, self-care tip, safety-net item and red-flag rule cites a `(source_id, quote)` pair. At runtime `KnowledgeStore.resolve_quote` locates the quote in a chunk; if it can't, the statement is dropped and listed under `validation.issues` instead of being shown without evidence. `tests/test_grounding_and_retrieval.py` fails if any quote is missing.
* **Retrieval** (`medassist/retrieval.py`): BM25 plus, when available, `paraphrase-multilingual-MiniLM-L12-v2` embeddings (cached in `knowledge/index/`). Results carry a relevance flag (minimum cosine similarity and lexical overlap) and can be filtered by topic. Assessments show up to two relevant retrieved passages per condition as "more from the sources", clearly separate from the cited claims.
* Queries are built from **canonical English symptom labels**, not the raw Hinglish text. In testing, Roman-script Hinglish queries retrieved poorly even with the multilingual model (e.g. "naak band hai aur chheenk aa rahi hai" scored below the relevance threshold for every chunk), while the normalised query found the right NHS section first.
* **Freshness**: each source's review date is shown; sources whose publisher review date has passed, or that were last reviewed more than 3 years ago, are flagged "may be outdated" in the UI.
* **Drift**: `python -m medassist.knowledge.verify_live` re-fetches the pages and checks every cited quote is still there. On 2026-10-21 all 255 quotes were present (the NHS UTI page was added on 2026-10-22).

## Licensing

NHS website content is published under the Open Government Licence v3.0; MedlinePlus health-topic and encyclopedia summaries are U.S. government works (some MedlinePlus encyclopedia content is licensed from A.D.A.M. — check before any redistribution beyond this prototype); WHO fact sheets are © WHO and reused here with attribution for non-commercial informational purposes. Every passage shown in the app links back to its source page.

## Known gaps — documents still needed

These could not be ingested and are needed before this is suitable for Indian users beyond a prototype:

1. **Ministry of Health and Family Welfare / National Health Portal (NHP India)** — `nhp.gov.in` did not resolve from the build environment, and `mohfw.gov.in` serves mostly navigation and PDF links. Wanted: NHP pages for common cold, allergic rhinitis, acidity/GERD, constipation, headache, urticaria, prickly heat.
2. **NCDC / NVBDCP guidance** on dengue, malaria and typhoid warning signs (fever is extremely common in India and these overlap with "flu-like illness"; currently only the WHO dengue fact sheet is used).
3. **ICMR Standard Treatment Workflows** for the in-scope conditions, for India-specific referral thresholds.
4. **CDC** pages (common cold, sore throat) — CDC returned HTTP 403 to automated requests; they are listed in the plan but not ingested.
5. **NICE Clinical Knowledge Summaries** (e.g. sore throat – acute, dyspepsia, constipation, headache – tension-type) would add clinician-facing criteria; not ingested because CKS content requires checking licence terms for reuse.

To add a source: append it to `sources.json` (choose a parser or add one in `ingest.py`), run the ingestion, then reference its quotes from the rule files and run the tests.

## Original WHO dataset

`dataset_OUR/` (76 diseases) was produced by an LLM summarising WHO fact sheets. It has no URLs or verbatim passages, so it is kept only for the `/graph` explorer and is not used as evidence.
