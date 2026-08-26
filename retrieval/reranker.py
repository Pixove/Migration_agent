from __future__ import annotations

from dataclasses import dataclass

from retrieval.documents import Document, RetrievalError


@dataclass
class RerankResult:
    document: Document
    score: float


class Reranker:
    """Cross-Encoder 重排接口。

    骨架阶段如果缺少 sentence-transformers，保持候选原始顺序，
    避免因为可选依赖未安装导致整条流程不可运行。
    """

    def __init__(self, model_name: str, enabled: bool = True) -> None:
        self.model_name = model_name
        self.enabled = enabled
        self._model = None

    def rerank(
        self,
        query: str,
        candidates: list[tuple[Document, float]],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        if not self.enabled or not candidates:
            return [
                RerankResult(document=doc, score=score)
                for doc, score in candidates
            ]

        try:
            if self._model is None:
                self._load_model()
            pairs = [(query, doc.text) for doc, _ in candidates]
            scores = self._model.predict(pairs)
        except Exception:
            # 模型加载或预测失败时保持原始顺序，避免阻塞主流程
            return [
                RerankResult(document=doc, score=score)
                for doc, score in candidates
            ]

        ranked = sorted(
            zip(candidates, scores),
            key=lambda pair: pair[1],
            reverse=True,
        )
        limit = top_k if top_k is not None else len(ranked)
        return [
            RerankResult(document=doc, score=float(score))
            for (doc, _), score in ranked[:limit]
        ]

    def _load_model(self) -> None:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RetrievalError(
                "未安装 sentence-transformers，重排请先执行: "
                "pip install sentence-transformers"
            ) from exc
        self._model = CrossEncoder(self.model_name)
