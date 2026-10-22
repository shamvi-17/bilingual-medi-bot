"""Runtime configuration, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PACKAGE_DIR = Path(__file__).parent
DATA_DIR = PACKAGE_DIR / "data"
KNOWLEDGE_DIR = PACKAGE_DIR / "knowledge"


def _bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Settings:
    groq_api_key: str | None = field(default_factory=lambda: os.environ.get("GROQ_API_KEY") or None)
    # Ordered fallback chain; models are tried until one responds.
    llm_models: list[str] = field(default_factory=lambda: [
        m.strip() for m in os.environ.get("LLM_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b").split(",") if m.strip()
    ])
    llm_enabled: bool = field(default_factory=lambda: _bool("MEDASSIST_LLM", True))
    llm_timeout: float = field(default_factory=lambda: float(os.environ.get("LLM_TIMEOUT", "20")))
    # "auto" uses multilingual sentence embeddings when available, else BM25 only.
    retrieval_mode: str = field(default_factory=lambda: os.environ.get("RETRIEVAL_MODE", "auto"))
    embedding_model: str = field(default_factory=lambda: os.environ.get(
        "EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    db_path: str = field(default_factory=lambda: os.environ.get(
        "MEDASSIST_DB", str(PACKAGE_DIR.parent / "instance" / "assessments.db")))
    max_followups: int = field(default_factory=lambda: int(os.environ.get("MAX_FOLLOWUPS", "8")))

    @property
    def llm_available(self) -> bool:
        return self.llm_enabled and bool(self.groq_api_key)


settings = Settings()
