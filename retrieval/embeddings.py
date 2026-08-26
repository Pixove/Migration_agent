from __future__ import annotations

from retrieval.documents import Document, RetrievalError


class VectorRetriever:
    """基于 Chroma 与 sentence-transformers 的向量语义检索。"""

    def __init__(
        self,
        model_name: str,
        enabled: bool = True,
        chroma_path: str = "kb/chroma",
    ) -> None:
        self.model_name = model_name
        self.enabled = enabled
        self.chroma_path = str(chroma_path)
        self._encoder = None
        self._collection = None
        self._docs: list[Document] = []

    def index(self, docs: list[Document]) -> None:
        self._docs = list(docs)
        if not self.enabled or not self._docs:
            return
        self._ensure()

        embeddings = self._encoder.encode(
            [doc.text for doc in self._docs],
            show_progress_bar=False,
        )
        ids = [
            f"{doc.doc_id}#{index}"
            for index, doc in enumerate(self._docs)
        ]
        metadatas = [
            {"doc_id": doc.doc_id, "source": doc.source}
            for doc in self._docs
        ]
        self._collection.upsert(
            ids=ids,
            embeddings=[vector.tolist() for vector in embeddings],
            metadatas=metadatas,
        )

    def search(self, query: str, top_k: int = 5) -> list[tuple[Document, float]]:
        if not self.enabled or not self._docs:
            return []
        self._ensure()

        query_vector = self._encoder.encode(
            [query],
            show_progress_bar=False,
        )[0]
        result = self._collection.query(
            query_embeddings=[query_vector.tolist()],
            n_results=top_k,
        )
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        by_id = {doc.doc_id: doc for doc in self._docs}

        hits: list[tuple[Document, float]] = []
        for doc_id, distance, metadata in zip(ids, distances, metadatas):
            doc = by_id.get((metadata or {}).get("doc_id"))
            if doc is not None:
                score = (
                    float(1.0 - distance)
                    if distance is not None
                    else 0.0
                )
                hits.append((doc, score))
        return hits

    def _ensure(self) -> None:
        if self._collection is not None:
            return
        try:
            import chromadb
        except ImportError as exc:
            raise RetrievalError(
                "未安装 chromadb，请先执行: pip install chromadb"
            ) from exc

        if self._encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RetrievalError(
                    "未安装 sentence-transformers，请先执行: "
                    "pip install sentence-transformers"
                ) from exc
            self._encoder = SentenceTransformer(self.model_name)

        client = chromadb.PersistentClient(path=self.chroma_path)
        self._collection = client.get_or_create_collection("migration")
