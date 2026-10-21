# Evaluation

```bash
python -m evaluation.run_eval
```

`scenarios.json` holds 35 short scripted scenarios: typical presentations (EN and Hinglish), overlapping symptoms (cold vs. allergy, skin rashes), ambiguous input, 10 emergency red-flag cases (including a meningitis combination spread over two messages and a red flag reached through a screening answer), 2 false-alarm checks ("I can't breathe through my nose", "chest burning … no chest pain"), refusal cases (only tiredness, out-of-scope symptoms, a child) and urgency checks. Each expected outcome cites the source passage that justifies it (`basis`), and the runner checks that passage exists in the corpus.

The runner reports candidate-condition recall, top-1 agreement, red-flag sensitivity and specificity, refusal correctness, urgency level, **citation correctness** (each displayed citation's quote is re-found in its chunk and its URL matches the source) and **evidence-grounding rate** (medical statements carrying a verified citation). Latest output: [results.md](results.md).

## Read these numbers with care

* **This is a software test, not a clinical validation.** Scenarios, expected outcomes and rules were all written by the same (non-clinician) author from NHS / MedlinePlus / WHO patient pages. No clinician has reviewed them.
* **The scenarios are in-sample.** They were written alongside the lexicon and rules, so 100% mostly shows the rules do what they were written to do.
* An informal held-out check was more informative: 20 phrasings written *after* the lexicon. Rules alone handled 7 correctly, missed 11 and **misattributed 2** ("pet mein gas" — *pet* = stomach — was read as "pets"; "gala chhil gaya … chubhta hai" was read as a prickly skin rash), and "chest feels heavy" missed the chest-pain red flag. All were fixed and added to `tests/test_extraction.py`, but this shows real-world wording will keep exposing gaps. With a Groq key, wording the rules miss falls back to validated LLM mapping; that path is not part of these deterministic numbers.
* Before any real use this needs: clinician review of `medassist/data/*.json` and the scenarios, a larger set of real (consented, de-identified) Hinglish symptom descriptions, and India-specific guidance in the corpus (see `docs/KNOWLEDGE_BASE.md`).
