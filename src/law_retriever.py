from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from .utils import read_json, tokenize, write_json


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def normalize_law_records(raw: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def add_record(law_id: Any, aid: Any, text: Any) -> None:
        if law_id is None or aid is None or text is None:
            return
        try:
            aid_int = int(aid)
        except (TypeError, ValueError):
            return
        records.append({"law_id": str(law_id), "aid": aid_int, "text": str(text)})

    def walk(node: Any, inherited_law_id: Any = None) -> None:
        if isinstance(node, list):
            for child in node:
                walk(child, inherited_law_id)
            return
        if not isinstance(node, dict):
            return
        law_id = node.get("law_id") or node.get("id_law") or node.get("lawId") or inherited_law_id
        if "aid" in node:
            text = node.get("content_Article") or node.get("text") or node.get("content") or node.get("article")
            add_record(law_id, node.get("aid"), text)
        for key in ("content", "articles", "provisions", "data", "items", "children"):
            if key in node and isinstance(node[key], list):
                for child in node[key]:
                    walk(child, law_id)

    walk(raw)
    unique: dict[tuple[str, int], dict[str, Any]] = {}
    for record in records:
        unique[(record["law_id"], record["aid"])] = record
    return list(unique.values())


class BM25LawRetriever:
    def __init__(self, records: list[dict[str, Any]], k1: float = 1.5, b: float = 0.75) -> None:
        self.records = records
        self.k1 = k1
        self.b = b
        self.doc_tokens = [tokenize(r.get("text", "")) for r in records]
        self.doc_lengths = [len(tokens) for tokens in self.doc_tokens]
        self.avgdl = sum(self.doc_lengths) / len(self.doc_lengths) if self.doc_lengths else 0.0
        self.term_freqs = [Counter(tokens) for tokens in self.doc_tokens]
        df: Counter[str] = Counter()
        for tokens in self.doc_tokens:
            df.update(set(tokens))
        total = max(1, len(self.doc_tokens))
        self.idf = {term: math.log(1 + (total - freq + 0.5) / (freq + 0.5)) for term, freq in df.items()}

    @classmethod
    def from_law_corpus(cls, path: str | Path) -> "BM25LawRetriever":
        return cls(normalize_law_records(read_json(path)))

    def search(self, query: str, top_k: int = 6) -> list[dict[str, Any]]:
        if not self.records:
            return []
        query_terms = tokenize(query)
        scores: list[tuple[float, int]] = []
        for idx, freqs in enumerate(self.term_freqs):
            score = 0.0
            doc_len = self.doc_lengths[idx] or 1
            for term in query_terms:
                if term not in freqs:
                    continue
                tf = freqs[term]
                denom = tf + self.k1 * (1 - self.b + self.b * doc_len / (self.avgdl or 1))
                score += self.idf.get(term, 0.0) * (tf * (self.k1 + 1)) / denom
            if score > 0:
                scores.append((score, idx))
        scores.sort(reverse=True)
        return [
            {
                "law_id": self.records[idx]["law_id"],
                "aid": self.records[idx]["aid"],
                "score": score,
                "text": self.records[idx]["text"],
            }
            for score, idx in scores[:top_k]
        ]

    def save_index(self, output_dir: str | Path) -> Path:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        index_path = output_dir / "index.json"
        write_json(index_path, {"records": self.records})
        return index_path


class BGEHybridLawRetriever:
    def __init__(
        self,
        records: list[dict[str, Any]],
        model_name: str = "BAAI/bge-m3",
        bm25_weight: float = 0.45,
        dense_weight: float = 0.55,
        batch_size: int = 16,
        max_length: int = 8192,
        fallback_to_bm25: bool = True,
    ) -> None:
        self.records = records
        self.bm25 = BM25LawRetriever(records)
        self.model_name = model_name
        self.bm25_weight = float(bm25_weight)
        self.dense_weight = float(dense_weight)
        self.batch_size = int(batch_size)
        self.max_length = int(max_length)
        self.fallback_to_bm25 = bool(fallback_to_bm25)
        self.model: Any | None = None
        self.doc_embeddings: Any | None = None
        self._load_dense_model()

    @classmethod
    def from_law_corpus(
        cls,
        path: str | Path,
        model_name: str = "BAAI/bge-m3",
        bm25_weight: float = 0.45,
        dense_weight: float = 0.55,
        batch_size: int = 16,
        max_length: int = 8192,
        fallback_to_bm25: bool = True,
    ) -> "BGEHybridLawRetriever":
        return cls(
            normalize_law_records(read_json(path)),
            model_name=model_name,
            bm25_weight=bm25_weight,
            dense_weight=dense_weight,
            batch_size=batch_size,
            max_length=max_length,
            fallback_to_bm25=fallback_to_bm25,
        )

    @property
    def dense_available(self) -> bool:
        return self.model is not None and self.doc_embeddings is not None

    def _load_dense_model(self) -> None:
        try:
            from FlagEmbedding import BGEM3FlagModel
        except ImportError as exc:
            if self.fallback_to_bm25:
                print(
                    "Warning: FlagEmbedding is unavailable; falling back to BM25 law retrieval.",
                    file=sys.stderr,
                )
                return
            raise RuntimeError("Install FlagEmbedding to use BGE-M3 law retrieval.") from exc

        try:
            self.model = BGEM3FlagModel(self.model_name, use_fp16=True)
            texts = [str(record.get("text", "")) for record in self.records]
            encoded = self.model.encode(
                texts,
                batch_size=self.batch_size,
                max_length=self.max_length,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            self.doc_embeddings = encoded["dense_vecs"]
        except Exception as exc:
            self.model = None
            self.doc_embeddings = None
            if self.fallback_to_bm25:
                print(
                    f"Warning: could not initialize {self.model_name}; falling back to BM25 law retrieval: {exc}",
                    file=sys.stderr,
                )
                return
            raise

    @staticmethod
    def _normalize_scores(scores: dict[int, float]) -> dict[int, float]:
        if not scores:
            return {}
        values = list(scores.values())
        low = min(values)
        high = max(values)
        if math.isclose(low, high):
            return {idx: 1.0 for idx in scores}
        return {idx: (score - low) / (high - low) for idx, score in scores.items()}

    @staticmethod
    def _cosine_scores(query_embedding: Any, doc_embeddings: Any) -> dict[int, float]:
        try:
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("Install numpy to use dense law retrieval scoring.") from exc

        query = np.asarray(query_embedding, dtype=np.float32)
        docs = np.asarray(doc_embeddings, dtype=np.float32)
        query_norm = np.linalg.norm(query) or 1.0
        doc_norms = np.linalg.norm(docs, axis=1)
        doc_norms[doc_norms == 0] = 1.0
        values = docs @ query / (doc_norms * query_norm)
        return {idx: float(score) for idx, score in enumerate(values)}

    def _dense_scores(self, query: str) -> dict[int, float]:
        if not self.dense_available:
            return {}
        encoded = self.model.encode(
            [query],
            batch_size=1,
            max_length=self.max_length,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return self._cosine_scores(encoded["dense_vecs"][0], self.doc_embeddings)

    def search(self, query: str, top_k: int = 6) -> list[dict[str, Any]]:
        if not self.dense_available:
            return self.bm25.search(query, top_k)

        bm25_hits = self.bm25.search(query, max(top_k * 8, 50))
        bm25_raw: dict[int, float] = {}
        key_to_idx = {(record["law_id"], int(record["aid"])): idx for idx, record in enumerate(self.records)}
        for hit in bm25_hits:
            idx = key_to_idx.get((hit["law_id"], int(hit["aid"])))
            if idx is not None:
                bm25_raw[idx] = float(hit["score"])

        dense_raw = self._dense_scores(query)
        bm25_scores = self._normalize_scores(bm25_raw)
        dense_scores = self._normalize_scores(dense_raw)
        candidate_ids = set(bm25_scores) | set(dense_scores)
        merged = [
            (
                self.bm25_weight * bm25_scores.get(idx, 0.0)
                + self.dense_weight * dense_scores.get(idx, 0.0),
                idx,
            )
            for idx in candidate_ids
        ]
        merged.sort(reverse=True)
        return [
            {
                "law_id": self.records[idx]["law_id"],
                "aid": self.records[idx]["aid"],
                "score": score,
                "text": self.records[idx]["text"],
            }
            for score, idx in merged[:top_k]
        ]


def build_law_retriever(config: dict[str, Any], law_corpus_path: str | Path) -> BM25LawRetriever | BGEHybridLawRetriever:
    law_cfg = config.get("law_retrieval", {})
    method = str(law_cfg.get("method", "bm25")).lower()
    if method in {"bm25_bge_m3", "bge_m3", "hybrid_bge_m3"}:
        return BGEHybridLawRetriever.from_law_corpus(
            law_corpus_path,
            model_name=str(law_cfg.get("embedding_model_name", "BAAI/bge-m3")),
            bm25_weight=float(law_cfg.get("bm25_weight", 0.45)),
            dense_weight=float(law_cfg.get("dense_weight", 0.55)),
            batch_size=int(law_cfg.get("embedding_batch_size", 16)),
            max_length=int(law_cfg.get("embedding_max_length", 8192)),
            fallback_to_bm25=_as_bool(law_cfg.get("dense_fallback_to_bm25"), default=True),
        )
    return BM25LawRetriever.from_law_corpus(law_corpus_path)


def load_law_keys(path: str | Path) -> set[tuple[str, int]]:
    return {(r["law_id"], int(r["aid"])) for r in normalize_law_records(read_json(path))}
