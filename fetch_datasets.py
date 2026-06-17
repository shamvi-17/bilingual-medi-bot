"""
Fetches accurate medical data from WHO fact sheets and structures it with Groq LLM.
Run: python3 fetch_datasets.py
"""

import requests, json, time, re, os, sys
from pathlib import Path
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])
OUT = Path("dataset_OUR")
OUT.mkdir(exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# ── Disease → WHO fact sheet URL mapping ──────────────────────────────────────
DISEASES = {
    "Dengue":                        "https://www.who.int/news-room/fact-sheets/detail/dengue-and-severe-dengue",
    "Malaria":                       "https://www.who.int/news-room/fact-sheets/detail/malaria",
    "Diabetes":                      "https://www.who.int/news-room/fact-sheets/detail/diabetes",
    "Tuberculosis":                  "https://www.who.int/news-room/fact-sheets/detail/tuberculosis",
    "HIV and AIDS":                  "https://www.who.int/news-room/fact-sheets/detail/hiv-aids",
    "Hepatitis A":                   "https://www.who.int/news-room/fact-sheets/detail/hepatitis-a",
    "Hepatitis B":                   "https://www.who.int/news-room/fact-sheets/detail/hepatitis-b",
    "Hepatitis C":                   "https://www.who.int/news-room/fact-sheets/detail/hepatitis-c",
    "Hepatitis D":                   "https://www.who.int/news-room/fact-sheets/detail/hepatitis-d",
    "Hepatitis E":                   "https://www.who.int/news-room/fact-sheets/detail/hepatitis-e",
    "Cholera":                       "https://www.who.int/news-room/fact-sheets/detail/cholera",
    "COVID-19":                      "https://www.who.int/news-room/fact-sheets/detail/coronavirus-disease-(covid-19)",
    "Influenza (Seasonal)":          "https://www.who.int/news-room/fact-sheets/detail/influenza-(seasonal)",
    "Mpox":                          "https://www.who.int/news-room/fact-sheets/detail/mpox",
    "Ebola":                         "https://www.who.int/news-room/fact-sheets/detail/ebola-virus-disease",
    "Measles":                       "https://www.who.int/news-room/fact-sheets/detail/measles",
    "Meningitis":                    "https://www.who.int/news-room/fact-sheets/detail/meningitis",
    "Hypertension":                  "https://www.who.int/news-room/fact-sheets/detail/hypertension",
    "Asthma":                        "https://www.who.int/news-room/fact-sheets/detail/asthma",
    "Chronic Obstructive Pulmonary Disease (COPD)": "https://www.who.int/news-room/fact-sheets/detail/chronic-obstructive-pulmonary-disease-(copd)",
    "Epilepsy":                      "https://www.who.int/news-room/fact-sheets/detail/epilepsy",
    "Dementia":                      "https://www.who.int/news-room/fact-sheets/detail/dementia",
    "Depression":                    "https://www.who.int/news-room/fact-sheets/detail/depression",
    "Anxiety Disorders":             "https://www.who.int/news-room/fact-sheets/detail/anxiety-disorders",
    "Bipolar Disorder":              "https://www.who.int/news-room/fact-sheets/detail/bipolar-disorder",
    "Schizophrenia":                 "https://www.who.int/news-room/fact-sheets/detail/schizophrenia",
    "Autism":                        "https://www.who.int/news-room/fact-sheets/detail/autism-spectrum-disorders",
    "Cancer":                        "https://www.who.int/news-room/fact-sheets/detail/cancer",
    "Breast Cancer":                 "https://www.who.int/news-room/fact-sheets/detail/breast-cancer",
    "Cervical Cancer":               "https://www.who.int/news-room/fact-sheets/detail/cervical-cancer",
    "Lung Cancer":                   "https://www.who.int/news-room/fact-sheets/detail/lung-cancer",
    "Colorectal Cancer":             "https://www.who.int/news-room/fact-sheets/detail/colorectal-cancer",
    "Leishmaniasis":                 "https://www.who.int/news-room/fact-sheets/detail/leishmaniasis",
    "Chagas Disease":                "https://www.who.int/news-room/fact-sheets/detail/chagas-disease-(american-trypanosomiasis)",
    "Leprosy":                       "https://www.who.int/news-room/fact-sheets/detail/leprosy",
    "Rabies":                        "https://www.who.int/news-room/fact-sheets/detail/rabies",
    "Typhoid":                       "https://www.who.int/news-room/fact-sheets/detail/typhoid",
    "Malnutrition":                  "https://www.who.int/news-room/fact-sheets/detail/malnutrition",
    "Anaemia":                       "https://www.who.int/news-room/fact-sheets/detail/anaemia",
    "Diarrhoeal Disease":            "https://www.who.int/news-room/fact-sheets/detail/diarrhoeal-disease",
    "Pneumonia":                     "https://www.who.int/news-room/fact-sheets/detail/pneumonia",
    "Stroke":                        "https://www.who.int/news-room/fact-sheets/detail/the-top-10-causes-of-death",
    "Gonorrhoea":                    "https://www.who.int/news-room/fact-sheets/detail/gonorrhoea-(neisseria-gonorrhoeae-infection)",
    "Syphilis":                      "https://www.who.int/news-room/fact-sheets/detail/syphilis",
    "Chlamydia":                     "https://www.who.int/news-room/fact-sheets/detail/chlamydia",
    "Herpes Simplex Virus":          "https://www.who.int/news-room/fact-sheets/detail/herpes-simplex-virus",
    "Human Papillomavirus (HPV)":    "https://www.who.int/news-room/fact-sheets/detail/human-papillomavirus-(hpv)-and-cervical-cancer",
    "Lassa Fever":                   "https://www.who.int/news-room/fact-sheets/detail/lassa-fever",
    "Marburg Virus Disease":         "https://www.who.int/news-room/fact-sheets/detail/marburg-virus-disease",
    "Japanese Encephalitis":         "https://www.who.int/news-room/fact-sheets/detail/japanese-encephalitis",
    "Diphtheria":                    "https://www.who.int/news-room/fact-sheets/detail/diphtheria",
    "Pertussis (Whooping Cough)":    "https://www.who.int/news-room/fact-sheets/detail/pertussis",
    "Tetanus":                       "https://www.who.int/news-room/fact-sheets/detail/tetanus",
    "Polio":                         "https://www.who.int/news-room/fact-sheets/detail/poliomyelitis",
    "Schistosomiasis":               "https://www.who.int/news-room/fact-sheets/detail/schistosomiasis",
    "Lymphatic Filariasis":          "https://www.who.int/news-room/fact-sheets/detail/lymphatic-filariasis",
    "Brucellosis":                   "https://www.who.int/news-room/fact-sheets/detail/brucellosis",
    "Endometriosis":                 "https://www.who.int/news-room/fact-sheets/detail/endometriosis",
    "Multiple Sclerosis":            "https://www.who.int/news-room/fact-sheets/detail/multiple-sclerosis",
    "Low Back Pain":                 "https://www.who.int/news-room/fact-sheets/detail/low-back-pain",
    "Migraine":                      "https://www.who.int/news-room/fact-sheets/detail/headache-disorders",
    "Meningococcal Disease":         "https://www.who.int/news-room/fact-sheets/detail/meningococcal-disease",
    "Echinococcosis":                "https://www.who.int/news-room/fact-sheets/detail/echinococcosis",
    "Listeriosis":                   "https://www.who.int/news-room/fact-sheets/detail/listeriosis",
    "Legionellosis":                 "https://www.who.int/news-room/fact-sheets/detail/legionellosis",
    "Infertility":                   "https://www.who.int/news-room/fact-sheets/detail/infertility",
    "Bacterial Vaginosis":           "https://www.who.int/news-room/fact-sheets/detail/bacterial-vaginosis",
    "Dracunculiasis (Guinea-Worm)":  "https://www.who.int/news-room/fact-sheets/detail/dracunculiasis-(guinea-worm-disease)",
    "Buruli Ulcer":                  "https://www.who.int/news-room/fact-sheets/detail/buruli-ulcer-(mycobacterium-ulcerans-infection)",
    "Candidiasis":                   "https://www.who.int/news-room/fact-sheets/detail/fungal-diseases",
    "MERS-CoV":                      "https://www.who.int/news-room/fact-sheets/detail/middle-east-respiratory-syndrome-coronavirus-(mers-cov)",
    "Lead Poisoning":                "https://www.who.int/news-room/fact-sheets/detail/lead-poisoning-and-health",
    "Maternal Mortality":            "https://www.who.int/news-room/fact-sheets/detail/maternal-mortality",
}

STRUCTURE_PROMPT = """You are a medical data extractor. Given WHO fact sheet content about {disease}, extract ALL medical facts and return ONLY valid JSON — no markdown, no explanation.

Required JSON structure:
{{
  "disease": "{disease}",
  "source": "World Health Organization (WHO) – Fact Sheet",
  "overview": "Clear 2-3 sentence clinical overview of the disease.",
  "symptoms": [
    "List every specific symptom mentioned",
    "Include both common and severe symptoms",
    "Each item is a specific, concrete symptom"
  ],
  "diagnosis": [
    "Each diagnostic test or method mentioned",
    "Include lab tests, imaging, clinical criteria"
  ],
  "treatment": [
    "Each treatment approach, drug, or intervention",
    "Include both first-line and secondary treatments"
  ],
  "transmission": [
    "Each route of transmission",
    "Include vectors, direct contact, airborne, etc."
  ],
  "prevention": [
    "Each specific preventive measure",
    "Include vaccines, hygiene, behavioral changes"
  ],
  "risk_factors": [
    "Each risk factor or at-risk group",
    "Include demographics, comorbidities, exposures"
  ],
  "complications": [
    "Each serious complication if untreated"
  ],
  "key_facts": [
    "3-5 important epidemiological or clinical facts with numbers"
  ]
}}

WHO content:
{content}

Return ONLY the JSON object. No backticks, no markdown."""


def fetch_who_page(url: str) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Remove noise
        for tag in soup.find_all(["nav","header","footer","script","style",
                                   "aside","form","button","noscript"]):
            tag.decompose()

        # Try to find main content block
        main = (
            soup.find("div", class_=re.compile(r"sf-detail-body|article-body|fact-sheet", re.I)) or
            soup.find("article") or
            soup.find("main") or
            soup.find("div", {"id": re.compile(r"content|main", re.I)})
        )
        text = (main or soup.find("body")).get_text(separator="\n", strip=True)

        # Clean whitespace
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(lines)[:6000]
    except Exception as e:
        return f"FETCH_ERROR: {e}"


def structure_with_llm(disease: str, content: str) -> dict:
    if content.startswith("FETCH_ERROR"):
        return None

    prompt = STRUCTURE_PROMPT.format(disease=disease, content=content)

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000,
                temperature=0.05,
            )
            raw = resp.choices[0].message.content.strip()

            # Strip markdown fences if present
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
            raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)

            return json.loads(raw)
        except json.JSONDecodeError:
            if attempt == 2:
                print(f"    [FAIL] JSON parse failed after 3 attempts")
                return None
            time.sleep(2)
        except Exception as e:
            print(f"    [FAIL] LLM error: {e}")
            time.sleep(5)
    return None


def slug(name: str) -> str:
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_")


def main():
    total = len(DISEASES)
    success, skipped, failed = 0, 0, 0

    print(f"\n{'='*55}")
    print(f"  Fetching {total} disease fact sheets from WHO")
    print(f"{'='*55}\n")

    for i, (disease, url) in enumerate(DISEASES.items(), 1):
        fname = OUT / f"{slug(disease)}.json"
        # Skip if already fetched from WHO
        if fname.exists():
            try:
                existing = json.loads(fname.read_text())
                if "WHO" in existing.get("source", ""):
                    print(f"[{i:02d}/{total}] {disease} — already done, skipping")
                    skipped += 1
                    continue
            except: pass
        print(f"[{i:02d}/{total}] {disease}")

        # Fetch WHO page
        print(f"         Fetching: {url}")
        content = fetch_who_page(url)
        if content.startswith("FETCH_ERROR"):
            print(f"         [FAIL] {content}")
            failed += 1
            time.sleep(1)
            continue

        print(f"         Structuring with LLM...")
        data = structure_with_llm(disease, content)
        if not data:
            failed += 1
            time.sleep(1)
            continue

        # Validate minimum fields
        has_symptoms = bool(data.get("symptoms"))
        has_treatment = bool(data.get("treatment"))
        if not has_symptoms and not has_treatment:
            print(f"         [FAIL] Empty extraction, skipping")
            failed += 1
            time.sleep(1)
            continue

        with open(fname, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        s_count = len(data.get("symptoms", []))
        t_count = len(data.get("treatment", []))
        print(f"         [OK] Saved - {s_count} symptoms, {t_count} treatments")
        success += 1

        # Respect WHO rate limits
        time.sleep(1.5)

    print(f"\n{'='*55}")
    print(f"  Done: {success} saved, {failed} failed, {skipped} skipped")
    print(f"  Dataset: {OUT}/")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
