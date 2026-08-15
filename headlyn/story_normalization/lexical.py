from __future__ import annotations

from typing import Protocol


class LexicalScorer(Protocol):
    model_name: str

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        ...


class BgeM3LexicalScorer:
    """BGE-M3 sparse lexical scorer.

    The FlagEmbedding dependency is imported lazily so deterministic tests and
    artifact inspection do not require loading the multi-gigabyte model.
    """

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-m3",
        batch_size: int = 16,
        max_length: int = 512,
        use_fp16: bool = False,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_length = max_length
        self.use_fp16 = use_fp16
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:
            raise RuntimeError(
                "BGE-M3 requires FlagEmbedding. Install requirements.txt before running "
                "story normalization."
            ) from exc
        self.model = BGEM3FlagModel(model_name, use_fp16=use_fp16)

    def score_pairs(self, pairs: list[tuple[str, str]]) -> list[float]:
        if not pairs:
            return []
        sentences = [text for pair in pairs for text in pair]
        output = self.model.encode(
            sentences,
            batch_size=self.batch_size,
            max_length=self.max_length,
            return_dense=False,
            return_sparse=True,
            return_colbert_vecs=False,
        )
        weights = output["lexical_weights"]
        scores: list[float] = []
        for index in range(0, len(weights), 2):
            score = self.model.compute_lexical_matching_score(
                weights[index],
                weights[index + 1],
            )
            scores.append(clamp_score(float(score)))
        return scores


def clamp_score(value: float) -> float:
    return max(0.0, min(1.0, value))
