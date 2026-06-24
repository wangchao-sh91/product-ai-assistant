from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "384"))
DEFAULT_EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
DEFAULT_RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1")

_TOKEN_RE = re.compile(r"[\w.-]+|[^\s]", re.UNICODE)


@lru_cache(maxsize=1)
def embedding_tokenizer():
    return embedding_model().tokenizer


@lru_cache(maxsize=1)
def embedding_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(DEFAULT_EMBEDDING_MODEL, trust_remote_code=True)


@lru_cache(maxsize=1)
def rerank_model():
    from sentence_transformers import CrossEncoder

    if os.getenv("RERANK_ALLOW_DOWNLOAD", "0") != "1" and not is_model_cached(DEFAULT_RERANK_MODEL):
        raise RuntimeError(f"rerank model is not cached locally: {DEFAULT_RERANK_MODEL}")
    return CrossEncoder(DEFAULT_RERANK_MODEL, trust_remote_code=True)


def tokenize(text: str) -> list[str]:
    try:
        return embedding_tokenizer().tokenize(text)
    except Exception:
        return _TOKEN_RE.findall(text)


def count_tokens(text: str) -> int:
    return len(tokenize(text))


def _as_vector(value: Any) -> list[float]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    if value and isinstance(value[0], list):
        value = value[0]
    return [float(item) for item in value]


def is_model_cached(model_name: str) -> bool:
    hf_home = Path(os.getenv("HF_HOME", Path.home() / ".cache" / "huggingface"))
    model_dir = hf_home / "hub" / f"models--{model_name.replace('/', '--')}"
    snapshot_dir = model_dir / "snapshots"
    if not snapshot_dir.exists():
        return False
    if any(model_dir.glob("**/*.incomplete")):
        return False
    return any(snapshot.is_dir() and any(snapshot.iterdir()) for snapshot in snapshot_dir.iterdir())


def embed_text(text: str, dimension: int = EMBEDDING_DIMENSION) -> list[float]:
    vector = embedding_model().encode(text, normalize_embeddings=True)
    values = _as_vector(vector)
    if len(values) == dimension:
        return values
    if len(values) > dimension:
        return values[:dimension]
    return values + [0.0] * (dimension - len(values))


def rerank_texts(query: str, texts: list[str]) -> list[float]:
    if not texts:
        return []
    pairs = [(query, text[:2400]) for text in texts]
    scores = rerank_model().predict(pairs)
    return [float(score) for score in scores]
