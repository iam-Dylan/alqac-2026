#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.law_evidence import normalize_public_law_text, split_public_law_provisions


def map_label(label: str) -> str:
    if label in {"A_WIN", "PARTIAL_A_WIN"}:
        return "A_WIN"
    if label in {"B_WIN", "PARTIAL_B_WIN"}:
        return "B_WIN"
    raise ValueError(f"Unknown verdict label: {label}")


def load_json(path: str | Path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_pred_laws(values: list[str]) -> set[str]:
    return {normalize_public_law_text(v) for v in values if isinstance(v, str) and "|" in v and not v.rsplit("|", 1)[-1].isdigit()}


def evaluate(input_path: str | Path, submission_path: str | Path) -> dict[str, object]:
    gold = load_json(input_path)
    submission = {item["case_id"]: item for item in load_json(submission_path)}

    pairs: list[tuple[str, str]] = []
    predicted_law: set[tuple[str, str]] = set()
    gold_law: set[tuple[str, str]] = set()
    missing_cases: list[str] = []
    unmatched_internal_law = 0

    for case in gold:
        case_id = case["case_id"]
        item = submission.get(case_id)
        if item is None:
            missing_cases.append(case_id)
            continue
        y_true = map_label(case["verdict_label"])
        y_pred = item["prediction"]
        pairs.append((y_true, y_pred))

        for law in split_public_law_provisions(case.get("related_law_provisions", "")):
            gold_law.add((case_id, law))
        for law in item.get("law_evidence", []):
            if not isinstance(law, str):
                continue
            if law.rsplit("|", 1)[-1].isdigit():
                unmatched_internal_law += 1
                continue
            predicted_law.add((case_id, normalize_public_law_text(law)))

    correct = sum(y_true == y_pred for y_true, y_pred in pairs)
    true_positive = len(predicted_law & gold_law)
    precision = true_positive / len(predicted_law) if predicted_law else 0.0
    recall = true_positive / len(gold_law) if gold_law else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "cases": len(gold),
        "submitted_cases": len(submission),
        "missing_cases": missing_cases,
        "outcome_accuracy": correct / len(pairs) if pairs else 0.0,
        "outcome_correct": correct,
        "outcome_total": len(pairs),
        "gold_prediction_distribution": dict(Counter(y for y, _ in pairs)),
        "pred_prediction_distribution": dict(Counter(y for _, y in pairs)),
        "confusion": {f"{a}->{b}": n for (a, b), n in Counter(pairs).items()},
        "law_precision": precision,
        "law_recall": recall,
        "law_f1": f1,
        "law_true_positive": true_positive,
        "law_predicted": len(predicted_law),
        "law_gold": len(gold_law),
        "unmatched_internal_law_items": unmatched_internal_law,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate public ALQAC submission locally.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--submission", required=True)
    args = parser.parse_args()

    report = evaluate(args.input, args.submission)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report["missing_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
