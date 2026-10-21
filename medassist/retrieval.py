"""Hybrid retrieval over the medical corpus.

Lexical BM25 always runs (no extra dependencies). When sentence-transformers and
the multilingual MiniLM model are available, dense cosine similarity is blended
in, which lets Roman-script Hinglish and paraphrased queries reach the English
source text. Results carry their relevance scores and a pass/fail relevance
check so callers never present weakly related text as evidence.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
import threading
from pathlib import Path

import numpy as np

from .config import KNOWLEDGE_DIR, settings
from .knowledge.store import KnowledgeStore, get_store

log = logging.getLogger(__name__)

STOPWORDS = set("""a an the and or of to in on at for with by is are was be been it its this that these those you your
your you're can may might will would should could do does not no if as from have has had into than then there their
they them he she we our us about after before over under more most less such some any each very also other""".split())

DENSE_WEIGHT = 0.6
LEXICAL_WEIGHT = 0.4
MIN_DENSE = 0.35       # cosine similarity floor for a passage to count as relevant
MIN_LEXICAL = 0.15     # normalised BM25 floor when dense retrieval is unavailable


def tokenize(text: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", text.lower())
    out = []
    for t in toks:
        if t in STOPWORDS or len(t) < 2:
            continue
        # light stemming so "sneezing" ~ "sneeze", "headaches" ~ "headache"
        for suf in ("ing", "es", "s"):
            if t.endswith(suf) and len(t) - len(suf) >= 4:
                t = t[: -len(suf)]
                break
        out.append(t)
    return out


@dataclass
class Hit:
    chunk: dict
    score: float
    dense: float | None
    lexical: float
    relevant: bool

    def to_dict(self) -> dict:
        c = self.chunk
        return {
            "chunk_id": c["chunk_id"],
            "source_id": c["source_id"],
            "title": c["title"],
            "publisher": c["publisher"],
            "url": c["url"],
            "section": c["section"],
            "text": c["text"],
            "last_reviewed": c.get("last_reviewed"),
            "score": round(self.score, 3),
            "relevant": self.relevant,
        }


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.docs = docs
        self.k1, self.b = k1, b
        self.avgdl = sum(len(d) for d in docs) / max(len(docs), 1)
        self.tf = [Counter(d) for d in docs]
        df = Counter()
        for d in docs:
            df.update(set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(len(self.docs))
        for i, (tf, d) in enumerate(zip(self.tf, self.docs)):
            dl = len(d)
            s = 0.0
            for t in query:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out[i] = s
        return out


class Retriever:
    def __init__(self, store: KnowledgeStore | None = None, mode: str | None = None):
        self.store = store or get_store()
        self.mode = mode or settings.retrieval_mode
        self.chunks = self.store.chunks
        texts = [f"{c['title']} {c['section']} {c['text']}" for c in self.chunks]
        self.bm25 = BM25([tokenize(t) for t in texts]) if texts else None
        self.encoder = None
        self.embeddings: np.ndarray | None = None
        self.dense_error: str | None = None
        if self.mode in ("auto", "dense") and texts:
            self._init_dense(texts)

    # ── dense index ──────────────────────────────────────────────────────────
    def _init_dense(self, texts: list[str]) -> None:
        os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        try:
            from sentence_transformers import SentenceTransformer  # optional dependency
            from transformers.utils import logging as hf_logging
            hf_logging.disable_progress_bar()

            digest = hashlib.sha1(("\n".join(texts) + settings.embedding_model).encode()).hexdigest()[:16]
            cache = KNOWLEDGE_DIR / "index" / f"embeddings-{digest}.npy"
            self.encoder = SentenceTransformer(settings.embedding_model)
            if cache.exists():
                self.embeddings = np.load(cache)
            else:
                emb = self.encoder.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
                self.embeddings = np.asarray(emb, dtype=np.float32)
                cache.parent.mkdir(parents=True, exist_ok=True)
                np.save(cache, self.embeddings)
        except Exception as e:  # missing package/model offline → lexical-only
            self.encoder, self.embeddings = None, None
            self.dense_error = f"{type(e).__name__}: {e}"[:200]
            log.warning("Dense retrieval unavailable, using BM25 only: %s", self.dense_error)

    @property
    def backend(self) -> str:
        if not self.chunks:
            return "unavailable"
        return "hybrid (multilingual embeddings + BM25)" if self.embeddings is not None else "lexical (BM25)"

    # ── search ───────────────────────────────────────────────────────────────
    def search(self, query: str, k: int = 5, topics: list[str] | None = None,
               exclude_sections: str | None = None) -> list[Hit]:
        if not self.chunks or not query.strip():
            return []
        lex = self.bm25.scores(tokenize(query))
        lex_norm = lex / lex.max() if lex.max() > 0 else lex
        dense = None
        if self.embeddings is not None and self.encoder is not None:
            q = self.encoder.encode([query], normalize_embeddings=True, show_progress_bar=False)[0]
            dense = self.embeddings @ q
        idx = range(len(self.chunks))
        if topics:
            tset = set(topics)
            idx = [i for i in idx if tset & set(self.chunks[i]["topics"])]
        if exclude_sections:
            pat = re.compile(exclude_sections, re.I)
            idx = [i for i in idx if not pat.search(self.chunks[i]["section"] or "")]
        hits = []
        for i in idx:
            d = float(dense[i]) if dense is not None else None
            score = (DENSE_WEIGHT * d + LEXICAL_WEIGHT * lex_norm[i]) if d is not None else float(lex_norm[i])
            # source prioritisation: primary pages for a topic get a small boost
            if self.chunks[i].get("priority", 2) == 1:
                score += 0.03
            relevant = bool((d is not None and d >= MIN_DENSE and lex[i] > 0) or (d is None and lex_norm[i] >= MIN_LEXICAL))
            hits.append(Hit(self.chunks[i], float(score), d, float(lex_norm[i]), relevant))
        hits.sort(key=lambda h: -h.score)
        return hits[:k]


_retriever: Retriever | None = None
_retriever_lock = threading.Lock()


def get_retriever() -> Retriever:
    global _retriever
    with _retriever_lock:   # warm-up thread and first request must not both build the index
        if _retriever is None:
            _retriever = Retriever()
        return _retriever
