from __future__ import annotations

from retrieval.documents import Document, RetrievalError


class VectorRetriever:
    """向量语义检索接口，骨架阶段默认关闭。"""

    def __init__(self, model_name: str, enabled: bool = True) -> None:
        self.model_name = model_name
        self.enabled = enabled
        self._encoder = None
        self._docs: list[Document] = []
        self._vectors = None

    def index(self, docs: list[Document]) -> None:
        self._docs = list(docs)
        if not self.enabled or not self._docs:
            return
        self._load_encoder()
        self._vectors = self._encoder.encode(
            [doc.text for doc in self._docs],
            show_progress_bar=False,
        )

    def search(self, query: str, top_k: int = 5) -> list[tuple[Document, float]]:
        if not self.enabled or not self._docs or self._vectors is None:
            return []

        self._load_encoder()
        try:
            import numpy as np
        except ImportError as exc:
            raise RetrievalError("未安装 numpy，请先执行: pip install numpy") from exc

        query_vector = self._encoder.encode([query], show_progress_bar=False)[0]
        scores = np.asarray(self._vectors) @ np.asarray(query_vector)
        order = np.argsort(scores)[::-1][:top_k]
        return [
            (self._docs[int(index)], float(scores[int(index)]))
            for index in order
        ]

    def _load_encoder(self) -> None:
        if self._encoder is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RetrievalError(
                "未安装 sentence-transformers，向量检索请先执行: "
                "pip install sentence-transformers"
            ) from exc
        self._encoder = SentenceTransformer(self.model_name)
