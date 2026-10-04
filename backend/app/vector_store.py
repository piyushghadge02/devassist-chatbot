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
        # Row i is the (already normalised) embedding for chunks[i]. Kept so a single
        # source can be removed: faiss IndexFlatIP exposes no remove_ids, so removal
        # has to rebuild the index from the surviving vectors.
        self.vectors: list[np.ndarray] = []
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
        self.vectors.extend(emb[i] for i in range(emb.shape[0]))
        return len(chunks)
    def search(self, query_embedding: np.ndarray, top_k: int = 3, source: str | None = None) -> list[str]:
        """SRS: retrieval is Top 3. Optionally filter by source document."""
        if len(self.chunks) == 0: return []
        k = min(top_k, len(self.chunks))
        q = np.array(query_embedding, dtype="float32")
        if q.ndim == 1: q = q.reshape(1, -1)
        if _HAS_FAISS:
            faiss.normalize_L2(q); _, idx = self._index.search(q, k); indices = idx[0].tolist()
        else:
            n = np.linalg.norm(q); qn = q / n if n else q
            scores = (self._matrix @ qn.T).ravel(); indices = np.argsort(-scores)[:k].tolist()
        if source is not None:
            indices = [i for i in indices if 0 <= i < len(self.chunks) and self.sources[i] == source]
        return [self.chunks[i] for i in indices if 0 <= i < len(self.chunks)]
    def clear(self):
        self.chunks.clear(); self.sources.clear(); self.vectors.clear()
        self._index = faiss.IndexFlatIP(self.dim) if _HAS_FAISS else None; self._matrix = None

    def remove_source(self, source: str) -> int:
        """Drop every chunk indexed from `source`. Returns the number of chunks removed.

        IndexFlatIP cannot delete rows in place, so the index is rebuilt from the
        retained vectors. Correct (not approximate) as long as vectors and chunks
        stay index-aligned, which add() guarantees."""
        if not self.chunks:
            return 0
        keep = [i for i, s in enumerate(self.sources) if s != source]
        removed = len(self.sources) - len(keep)
        if removed == 0:
            return 0
        if _HAS_FAISS:
            self._index = faiss.IndexFlatIP(self.dim)
            if keep:
                self._index.add(np.array([self.vectors[i] for i in keep], dtype="float32"))
        elif keep:
            self._matrix = np.vstack([self._matrix[i] for i in keep])
        else:
            self._matrix = None
        self.chunks = [self.chunks[i] for i in keep]
        self.sources = [self.sources[i] for i in keep]
        self.vectors = [self.vectors[i] for i in keep]
        return removed
