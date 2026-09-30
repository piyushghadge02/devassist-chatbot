import hashlib, math
import numpy as np

DIM = 384  # all-MiniLM-L6-v2 dimension

class HashEmbedder:
    """Deterministic offline embedder (same dimension as MiniLM). Used when
    sentence-transformers / model download is unavailable, and in tests."""
    name = "hash-fallback"
    def encode(self, texts: list[str]) -> np.ndarray:
        out = []
        for t in texts:
            vec = np.zeros(DIM, dtype="float32")
            tokens = t.lower().split() or [""]
            for tok in tokens:
                h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
                vec[h % DIM] += 1.0
                vec[(h >> 8) % DIM] += 0.5
            n = np.linalg.norm(vec)
            out.append(vec / n if n else vec)
        return np.array(out, dtype="float32")

class SentenceTransformerEmbedder:
    name = "sentence-transformers/all-MiniLM-L6-v2"
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)
    def encode(self, texts: list[str]) -> np.ndarray:
        v = self._model.encode(texts, normalize_embeddings=True)
        return np.array(v, dtype="float32")

def get_embedder(backend: str = "auto", model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
    if backend == "hash":
        return HashEmbedder()
    if backend == "sentence-transformers":
        return SentenceTransformerEmbedder(model_name)
    try:  # auto
        return SentenceTransformerEmbedder(model_name)
    except Exception:
        return HashEmbedder()
