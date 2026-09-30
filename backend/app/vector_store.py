import numpy as np
try:
    import faiss
    _HAS_FAISS = True
except Exception:
    faiss = None
    _HAS_FAISS = False

class VectorStore:
    """In-memory FAISS store (SRS 3.3). Falls back to a NumPy cosine index with
    the identical interface when faiss-cpu is not installed, so the app never crashes."""
    def __init__(self, dim: int = 384):
        self.dim = dim
        self.chunks: list[str] = []
        self.sources: list[str] = []
        self._index = faiss.IndexFlatIP(dim) if _HAS_FAISS else None
        self._matrix: np.ndarray | None = None
    @property
    def backend(self): return "faiss" if _HAS_FAISS else "numpy-fallback"
    def __len__(self): return len(self.chunks)
    def add(self, embeddings: np.ndarray, chunks: list[str], source: str = "") -> int:
        if embeddings is None or len(chunks) == 0: return 0
        emb = np.array(embeddings, dtype="float32")
        if emb.ndim == 1: emb = emb.reshape(1, -1)
        if _HAS_FAISS:
            faiss.normalize_L2(emb); self._index.add(emb)
        else:
            norms = np.linalg.norm(emb, axis=1, keepdims=True); norms[norms == 0] = 1
            emb = emb / norms
            self._matrix = emb if self._matrix is None else np.vstack([self._matrix, emb])
        self.chunks.extend(chunks); self.sources.extend([source] * len(chunks))
        return len(chunks)
    def search(self, query_embedding: np.ndarray, top_k: int = 3) -> list[str]:
        """SRS: retrieval is Top 3."""
        if len(self.chunks) == 0: return []
        k = min(top_k, len(self.chunks))
        q = np.array(query_embedding, dtype="float32")
        if q.ndim == 1: q = q.reshape(1, -1)
        if _HAS_FAISS:
            faiss.normalize_L2(q); _, idx = self._index.search(q, k); indices = idx[0].tolist()
        else:
            n = np.linalg.norm(q); qn = q / n if n else q
            scores = (self._matrix @ qn.T).ravel(); indices = np.argsort(-scores)[:k].tolist()
        return [self.chunks[i] for i in indices if 0 <= i < len(self.chunks)]
    def clear(self):
        self.chunks.clear(); self.sources.clear()
        self._index = faiss.IndexFlatIP(self.dim) if _HAS_FAISS else None; self._matrix = None
