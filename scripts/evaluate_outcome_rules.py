#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_public import map_label
from src.outcome_predictor import predict_outcome
from src.query_parser import parse_case_query


def load_json(path: str | Path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate outcome rules using public court_verdict text.")
    parser.add_argument("--input", required=True)
    args = parser.parse_args()

    data = load_json(args.input)
    pairs: list[tuple[str, str]] = []
    wrong: list[dict[str, str]] = []
    for case in data:
        parsed = parse_case_query(case["case_query"])
        segments = [
            {
                "chunk_id": f"{case['case_id']}_gold_verdict",
                "text": case.get("court_verdict") or case.get("judgment_text") or "",
                "score": 1.0,
            }
        ]
        pred = predict_outcome(case["case_query"], segments, parsed)
        y_true = map_label(case["verdict_label"])
        y_pred = pred["prediction"]
        pairs.append((y_true, y_pred))
        if y_true != y_pred:
            wrong.append(
                {
                    "case_id": case["case_id"],
                    "gold": y_true,
                    "pred": y_pred,
                    "label": case["verdict_label"],
                    "rationale": pred["rationale"],
                }
            )

    correct = sum(a == b for a, b in pairs)
    report = {
        "outcome_accuracy": correct / len(pairs) if pairs else 0.0,
        "correct": correct,
        "total": len(pairs),
        "gold_distribution": dict(Counter(a for a, _ in pairs)),
        "pred_distribution": dict(Counter(b for _, b in pairs)),
        "confusion": {f"{a}->{b}": n for (a, b), n in Counter(pairs).items()},
        "wrong_sample": wrong[:20],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
