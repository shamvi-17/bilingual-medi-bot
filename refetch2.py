import requests, json, time, re, os
from pathlib import Path
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.environ["GROQ_API_KEY"])
OUT = Path("dataset_OUR")
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

REFETCH = {
    "Chlamydia":                    "https://www.who.int/news-room/fact-sheets/detail/chlamydia",
    "Diphtheria":                   "https://www.who.int/news-room/fact-sheets/detail/diphtheria",
    "Herpes Simplex Virus":         "https://www.who.int/news-room/fact-sheets/detail/herpes-simplex-virus",
    "Endometriosis":                "https://www.who.int/news-room/fact-sheets/detail/endometriosis",
    "Guillain-Barre Syndrome":      "https://www.who.int/news-room/fact-sheets/detail/guillain-barre-syndrome",
    "Echinococcosis":               "https://www.who.int/news-room/fact-sheets/detail/echinococcosis",
    "Dracunculiasis":               "https://www.who.int/news-room/fact-sheets/detail/dracunculiasis-(guinea-worm-disease)",
    "Chromoblastomycosis":          "https://www.who.int/news-room/fact-sheets/detail/chromoblastomycosis",
    "Candidiasis":                  "https://www.who.int/news-room/fact-sheets/detail/candidiasis",
    "Childhood Cancer":             "https://www.who.int/news-room/fact-sheets/detail/cancer-in-children",
    "Cancer":                       "https://www.who.int/news-room/fact-sheets/detail/cancer",
}

PROMPT = """Extract medical facts from this WHO page about {disease}. Return ONLY valid JSON, no markdown:
{{
  "disease": "{disease}",
  "source": "World Health Organization (WHO) – Fact Sheet",
  "overview": "2-3 sentence clinical overview.",
  "symptoms": ["short symptom term under 50 chars each. Extract ALL symptoms mentioned, even indirectly."],
  "diagnosis": ["diagnostic test or method"],
  "treatment": ["treatment approach"],
  "transmission": ["route of transmission"],
  "prevention": ["prevention measure"],
  "risk_factors": ["risk factor"],
  "complications": ["complication"],
  "key_facts": ["important epidemiological stat"]
}}

IMPORTANT: For symptoms, extract every clinical sign and symptom mentioned anywhere in the text.
For example if text mentions "fever, fatigue, painful blisters", symptoms should be ["fever", "fatigue", "painful blisters"].
Content: {content}"""

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup.find_all(["nav","header","footer","script","style","aside"]):
            tag.decompose()
        main = soup.find("article") or soup.find("main") or soup.find("body")
        lines = [l.strip() for l in main.get_text(separator="\n").splitlines() if l.strip()]
        return "\n".join(lines)[:6000]
    except Exception as e:
        return f"ERROR:{e}"

def slug(name):
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_")

# Map disease names to their existing file slugs to overwrite
SLUG_OVERRIDES = {
    "Guillain-Barre Syndrome":  "guillainbarré_syndrome",
    "Dracunculiasis":           "dracunculiasis_guinea_worm_disease",
    "Candidiasis":              "candidiasis_yeast_infection",
}

success = 0
for disease, url in REFETCH.items():
    print(f"  {disease}...", end=" ", flush=True)
    content = fetch(url)
    if content.startswith("ERROR"):
        print(f"fetch failed: {content}")
        continue
    for model in ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "gemma2-9b-it"]:
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role":"user","content": PROMPT.format(disease=disease, content=content)}],
                max_tokens=1500, temperature=0.05
            )
            raw = resp.choices[0].message.content.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
            raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
            data = json.loads(raw)
            file_slug = SLUG_OVERRIDES.get(disease, slug(disease))
            fname = OUT / f"{file_slug}.json"
            fname.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"[OK] ({len(data.get('symptoms',[]))} symptoms) -> {fname.name}")
            success += 1
            time.sleep(1.5)
            break
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                print(f"rate limit on {model}, trying next...")
                time.sleep(3)
                continue
            print(f"[FAIL] {e}")
            break

print(f"\nDone: {success}/{len(REFETCH)} saved")
