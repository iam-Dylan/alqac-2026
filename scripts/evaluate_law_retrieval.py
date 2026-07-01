#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.law_evidence import normalize_public_law_text, split_public_law_provisions
from src.law_retriever import build_law_retriever
from src.utils import load_config, read_json


def _hit_to_public_like(hit: dict[str, Any]) -> str:
    text = str(hit.get("text", ""))
    law_name = str(hit.get("law_name") or hit.get("law_id", ""))
    article = ""
    for marker in ("Điều ", "điều "):
        if marker in text:
            article = "Điều " + text.split(marker, 1)[1].split(".", 1)[0].split("\n", 1)[0].strip()
            break
    return normalize_public_law_text(f"{law_name} | {article}") if article else f"{law_name}|{hit['aid']}"


def evaluate(input_path: str | Path, law_corpus_path: str | Path, config_path: str | Path, method: str | None) -> dict[str, Any]:
    config = load_config(config_path)
    if method:
        config.setdefault("law_retrieval", {})["method"] = method
    data = read_json(input_path)
    retriever = build_law_retriever(config, law_corpus_path)
    top_k = int(config.get("law_retrieval", {}).get("top_k", 6))

    predicted: set[tuple[str, str]] = set()
    gold: set[tuple[str, str]] = set()
    for item in data:
        case_id = item["case_id"]
        query = str(item.get("case_query", ""))
        for law in split_public_law_provisions(str(item.get("related_law_provisions", ""))):
            gold.add((case_id, law))
        for hit in retriever.search(query, top_k):
            predicted.add((case_id, _hit_to_public_like(hit)))

    true_positive = len(predicted & gold)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    warnings = []
    if true_positive == 0 and predicted and gold:
        warnings.append(
            "Exact public law F1 may be zero because the provided law corpus uses internal law_id|aid "
            "while public gold related_law_provisions use human-readable law names. Use this script for "
            "same-format method comparison only, or add a law-name mapping before treating F1 as final."
        )
    return {
        "method": config.get("law_retrieval", {}).get("method", "bm25"),
        "cases": len(data),
        "law_true_positive": true_positive,
        "law_predicted": len(predicted),
        "law_gold": len(gold),
        "law_precision": precision,
        "law_recall": recall,
        "law_f1": f1,
        "dense_available": bool(getattr(retriever, "dense_available", False)),
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate law retrieval on public diagnostics without Retrieval API calls.")
    parser.add_argument("--input", default="data/ALQAC2026_public_test.json")
    parser.add_argument("--law-corpus", default="data/corpus_law_pub.json")
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--method", default=None, help="Override law_retrieval.method, e.g. bm25 or bm25_bge_m3.")
    args = parser.parse_args()

    report = evaluate(args.input, args.law_corpus, args.config, args.method)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
