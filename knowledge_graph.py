import json
import re
from pathlib import Path

class DiseaseKnowledgeGraph:
    def __init__(self, dataset_path: str):
        self.graph = {}
        self._load(dataset_path)
        self._build_symptom_index()

    def _load(self, path: str):
        seen = set()
        for file in Path(path).glob("*.json"):
            with open(file, encoding="utf-8") as f:
                data = json.load(f)

            name = data.get("disease") or data.get("topic") or \
                   file.stem.replace("_", " ").title()

            # Skip duplicates (old + new files for same disease)
            key = name.lower().strip()
            if key in seen:
                continue
            seen.add(key)

            def flatten(val):
                texts = []
                if isinstance(val, str): return [val]
                if isinstance(val, list):
                    for v in val:
                        texts.extend(flatten(v))
                if isinstance(val, dict):
                    for v in val.values():
                        texts.extend(flatten(v))
                return [t for t in texts if isinstance(t, str) and 3 < len(t) < 300]

            symptoms_raw = data.get("symptoms", [])
            if isinstance(symptoms_raw, dict):
                symptoms = []
                for v in symptoms_raw.values():
                    symptoms.extend(flatten(v))
            else:
                symptoms = flatten(symptoms_raw)

            self.graph[key] = {
                "name":          name,
                "symptoms":      symptoms[:15],
                "diagnosis":     flatten(data.get("diagnosis", []))[:8],
                "treatment":     flatten(data.get("treatment", []))[:8],
                "transmission":  flatten(data.get("transmission", []))[:5],
                "prevention":    flatten(data.get("prevention", []))[:5],
                "risk_factors":  flatten(data.get("risk_factors", []))[:5],
                "complications": flatten(data.get("complications", []))[:5],
                "key_facts":     flatten(data.get("key_facts", []))[:5],
                "overview":      str(data.get("overview", ""))[:600],
            }

    def _build_symptom_index(self):
        # English + Hinglish keywords
        KEYWORDS = [
            "fever", "headache", "cough", "fatigue", "rash", "pain", "nausea",
            "vomiting", "diarrhoea", "diarrhea", "bleeding", "swelling",
            "breathless", "seizure", "jaundice", "confusion", "weakness",
            "itching", "discharge", "chills", "sweating", "chest pain",
            "sore throat", "body ache", "joint pain", "muscle pain",
            "numbness", "ulcer", "skin lesion", "weight loss", "anaemia",
            "paralysis", "blindness", "dehydration", "inflammation", "infection",
            "anxiety", "depression", "memory loss", "tremor", "liver",
            "kidney", "abdominal pain", "back pain", "shortness of breath",
            "high blood pressure", "blurred vision", "frequent urination",
            "pale skin", "rapid heartbeat", "loss of appetite",
            # Hinglish
            "bukhar", "sar dard", "khansi", "thakan", "dard", "ulti",
            "khoon", "sujan", "saans", "kamzori", "khujli", "kapkapi",
            "seene mein dard", "gala dard", "badan dard",
        ]
        self.symptom_index = {}
        for disease, info in self.graph.items():
            all_text = " ".join(
                info["symptoms"] + info["risk_factors"] + info["complications"] + [info["overview"]]
            ).lower()
            for kw in KEYWORDS:
                if kw in all_text:
                    self.symptom_index.setdefault(kw, []).append(disease)

    def search_by_symptoms(self, user_text: str, top_k: int = 4) -> list[dict]:
        text = user_text.lower()
        scores = {}
        for kw, diseases in self.symptom_index.items():
            if kw in text:
                for d in diseases:
                    scores[d] = scores.get(d, 0) + 1
        ranked = sorted(scores.items(), key=lambda x: -x[1])
        return [self.graph[d] for d, _ in ranked[:top_k]]

    def get_by_name(self, name: str) -> dict | None:
        name_lower = name.lower()
        if name_lower in self.graph:
            return self.graph[name_lower]
        for key, info in self.graph.items():
            if name_lower in key or key in name_lower:
                return info
        return None

    def retrieve(self, user_text: str) -> list[dict]:
        """Main retrieval: symptom search + direct name match combined."""
        results = self.search_by_symptoms(user_text, top_k=3)
        found_names = {d["name"] for d in results}
        # Also check if user mentioned a disease name directly
        for word in user_text.lower().split():
            hit = self.get_by_name(word)
            if hit and hit["name"] not in found_names:
                results.insert(0, hit)
                results = results[:4]
        return results

    def format_context(self, diseases: list[dict]) -> str:
        if not diseases:
            return "No matching diseases found in knowledge base."
        blocks = []
        for d in diseases:
            lines = [f"DISEASE: {d['name']}"]
            if d["overview"]:
                lines.append(f"Overview: {d['overview'][:200]}")
            if d["symptoms"]:
                lines.append("Symptoms: " + " | ".join(d["symptoms"][:8]))
            if d["diagnosis"]:
                lines.append("Diagnosis: " + " | ".join(d["diagnosis"][:4]))
            if d["treatment"]:
                lines.append("Treatment: " + " | ".join(d["treatment"][:4]))
            if d["transmission"]:
                lines.append("Transmission: " + " | ".join(d["transmission"][:3]))
            if d["prevention"]:
                lines.append("Prevention: " + " | ".join(d["prevention"][:3]))
            if d["risk_factors"]:
                lines.append("Risk factors: " + " | ".join(d["risk_factors"][:3]))
            if d["complications"]:
                lines.append("Complications: " + " | ".join(d["complications"][:3]))
            if d["key_facts"]:
                lines.append("Key facts: " + " | ".join(d["key_facts"][:2]))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)