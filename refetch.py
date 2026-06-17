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
    "Cancer":                   "https://www.who.int/news-room/fact-sheets/detail/cancer",
    "Human Papillomavirus":     "https://www.who.int/news-room/fact-sheets/detail/human-papillomavirus-(hpv)-and-cervical-cancer",
    "Infertility":              "https://www.who.int/news-room/fact-sheets/detail/infertility",
    "Avian Influenza":          "https://www.who.int/news-room/fact-sheets/detail/influenza-(avian-and-other-zoonotic)",
    "Japanese Encephalitis":    "https://www.who.int/news-room/fact-sheets/detail/japanese-encephalitis",
    "Lassa Fever":              "https://www.who.int/news-room/fact-sheets/detail/lassa-fever",
    "Legionellosis":            "https://www.who.int/news-room/fact-sheets/detail/legionellosis",
    "Listeriosis":              "https://www.who.int/news-room/fact-sheets/detail/listeriosis",
    "Low Back Pain":            "https://www.who.int/news-room/fact-sheets/detail/low-back-pain",
    "Lymphatic Filariasis":     "https://www.who.int/news-room/fact-sheets/detail/lymphatic-filariasis",
    "Marburg Virus Disease":    "https://www.who.int/news-room/fact-sheets/detail/marburg-virus-disease",
    "Maternal Mortality":       "https://www.who.int/news-room/fact-sheets/detail/maternal-mortality",
    "Menopause":                "https://www.who.int/news-room/fact-sheets/detail/menopause",
    "Mental Disorders":         "https://www.who.int/news-room/fact-sheets/detail/mental-disorders",
    "Multiple Sclerosis":       "https://www.who.int/news-room/fact-sheets/detail/multiple-sclerosis",
    "Musculoskeletal Health":   "https://www.who.int/news-room/fact-sheets/detail/musculoskeletal-conditions",
    "Drug-Resistant Gonorrhoea":"https://www.who.int/news-room/fact-sheets/detail/gonorrhoea-(neisseria-gonorrhoeae-infection)",
    "Migraine":                 "https://www.who.int/news-room/fact-sheets/detail/headache-disorders",
    "MERS-CoV":                 "https://www.who.int/news-room/fact-sheets/detail/middle-east-respiratory-syndrome-coronavirus-(mers-cov)",
    "Injuries and Violence":    "https://www.who.int/news-room/fact-sheets/detail/injuries-and-violence",
    "Mental Health":            "https://www.who.int/news-room/fact-sheets/detail/mental-health-strengthening-our-response",
}

PROMPT = """Extract medical facts from this WHO page about {disease}. Return ONLY valid JSON, no markdown:
{{
  "disease": "{disease}",
  "source": "World Health Organization (WHO) – Fact Sheet",
  "overview": "2-3 sentence clinical overview.",
  "symptoms": ["short symptom term under 50 chars each"],
  "diagnosis": ["diagnostic test or method"],
  "treatment": ["treatment approach"],
  "transmission": ["route of transmission"],
  "prevention": ["prevention measure"],
  "risk_factors": ["risk factor"],
  "complications": ["complication"],
  "key_facts": ["important epidemiological stat"]
}}
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
        return "\n".join(lines)[:5000]
    except Exception as e:
        return f"ERROR:{e}"

def slug(name):
    return re.sub(r"[^\w]+", "_", name.lower()).strip("_")

success = 0
for disease, url in REFETCH.items():
    print(f"  {disease}...", end=" ", flush=True)
    content = fetch(url)
    if content.startswith("ERROR"):
        print(f"fetch failed: {content}")
        continue
    for model in ["llama-3.1-8b-instant", "gemma2-9b-it"]:
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
            fname = OUT / f"{slug(disease)}.json"
            fname.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            print(f"[OK] ({len(data.get('symptoms',[]))} symptoms)")
            success += 1
            time.sleep(1.2)
            break
        except Exception as e:
            if "rate_limit" in str(e).lower():
                continue
            print(f"[FAIL] {e}")
            break

print(f"\nDone: {success}/{len(REFETCH)} saved")
