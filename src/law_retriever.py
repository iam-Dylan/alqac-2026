from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

from .utils import read_json, tokenize, write_json


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


def load_law_keys(path: str | Path) -> set[tuple[str, int]]:
    return {(r["law_id"], int(r["aid"])) for r in normalize_law_records(read_json(path))}
