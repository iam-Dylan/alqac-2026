#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_public import map_label


DECISION_RE = re.compile(r"quyết định|tuyên xử|xử\s*:", re.IGNORECASE)
POSITIVE_RE = re.compile(
    r"chấp nhận(?:\s+một phần)?\s+yêu cầu|buộc\s+bị đơn|buộc.{0,80}(?:trả|thanh toán|bồi thường)",
    re.IGNORECASE,
)
NEGATIVE_RE = re.compile(
    r"không\s+chấp nhận\s+(?:toàn bộ\s+)?yêu cầu|bác\s+(?:toàn bộ\s+)?yêu cầu|không có căn cứ chấp nhận",
    re.IGNORECASE,
)


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def load_latest_logs(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    log_path = Path(path)
    if not log_path.exists():
        return {}
    latest: dict[str, dict[str, Any]] = {}
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            case_id = item.get("case_id")
            if case_id:
                latest[str(case_id)] = item
    return latest


def accuracy(rows: list[tuple[str, str]]) -> dict[str, Any]:
    if not rows:
        return {"accuracy": None, "correct": 0, "total": 0, "distribution": {}, "confusion": {}}
    correct = sum(gold == pred for gold, pred in rows)
    return {
        "accuracy": correct / len(rows),
        "correct": correct,
        "total": len(rows),
        "distribution": dict(Counter(pred for _, pred in rows)),
        "confusion": {f"{gold}->{pred}": n for (gold, pred), n in Counter(rows).items()},
    }


def prediction_from(value: Any) -> str | None:
    if isinstance(value, dict) and value.get("prediction") in {"A_WIN", "B_WIN"}:
        return str(value["prediction"])
    if value in {"A_WIN", "B_WIN"}:
        return str(value)
    return None


def evidence_stats(log: dict[str, Any] | None, gold_case: dict[str, Any]) -> dict[str, Any]:
    segments = []
    if log:
        segments = log.get("retrieved_segments") or []
    retrieved_text = "\n".join(str(seg.get("text", "")) for seg in segments if isinstance(seg, dict))
    verdict_text = str(gold_case.get("court_verdict", ""))
    reasoning_text = str(gold_case.get("court_reasoning", ""))
    query_text = str(gold_case.get("case_query", ""))

    retrieved_tokens = set(re.findall(r"[\wÀ-ỹ]+", retrieved_text.lower()))
    verdict_tokens = {tok for tok in re.findall(r"[\wÀ-ỹ]+", verdict_text.lower()) if len(tok) >= 4}
    reasoning_tokens = {tok for tok in re.findall(r"[\wÀ-ỹ]+", reasoning_text.lower()) if len(tok) >= 4}

    verdict_overlap = len(retrieved_tokens & verdict_tokens) / len(verdict_tokens) if verdict_tokens else 0.0
    reasoning_overlap = len(retrieved_tokens & reasoning_tokens) / len(reasoning_tokens) if reasoning_tokens else 0.0

    return {
        "retrieved_segments": len(segments),
        "retrieved_chars": len(retrieved_text),
        "has_decision_marker": bool(DECISION_RE.search(retrieved_text)),
        "has_positive_signal": bool(POSITIVE_RE.search(retrieved_text)),
        "has_negative_signal": bool(NEGATIVE_RE.search(retrieved_text)),
        "verdict_token_overlap": round(verdict_overlap, 4),
        "reasoning_token_overlap": round(reasoning_overlap, 4),
        "query_chars": len(query_text),
    }


def evaluate_source(
    gold_cases: list[dict[str, Any]],
    predictions: dict[str, str],
) -> dict[str, Any]:
    rows = []
    missing = []
    for case in gold_cases:
        case_id = str(case["case_id"])
        pred = predictions.get(case_id)
        if pred is None:
            missing.append(case_id)
            continue
        rows.append((map_label(str(case["verdict_label"])), pred))
    report = accuracy(rows)
    report["missing"] = missing
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose ALQAC outcome predictions and model-vs-rule behavior.")
    parser.add_argument("--input", required=True, help="Public input with verdict_label for diagnostics.")
    parser.add_argument("--submission", help="Final submission JSON to evaluate.")
    parser.add_argument("--logs", default="logs/prediction_logs.jsonl", help="Prediction logs JSONL from pipeline.")
    parser.add_argument("--wrong-limit", type=int, default=20)
    args = parser.parse_args()

    gold_cases = load_json(args.input)
    logs = load_latest_logs(args.logs)

    final_predictions: dict[str, str] = {}
    if args.submission:
        final_predictions = {
            str(item["case_id"]): str(item["prediction"])
            for item in load_json(args.submission)
            if item.get("prediction") in {"A_WIN", "B_WIN"}
        }

    log_final_predictions = {
        case_id: pred
        for case_id, item in logs.items()
        if (pred := prediction_from(item.get("prediction"))) is not None
    }
    rule_predictions = {
        case_id: pred
        for case_id, item in logs.items()
        if (pred := prediction_from(item.get("rule_prediction"))) is not None
    }
    model_predictions = {
        case_id: pred
        for case_id, item in logs.items()
        if (pred := prediction_from(item.get("model_prediction"))) is not None
    }

    report: dict[str, Any] = {
        "cases": len(gold_cases),
        "logs_available": len(logs),
        "final_submission": evaluate_source(gold_cases, final_predictions) if final_predictions else None,
        "log_final": evaluate_source(gold_cases, log_final_predictions) if log_final_predictions else None,
        "rule_only": evaluate_source(gold_cases, rule_predictions) if rule_predictions else None,
        "model_only": evaluate_source(gold_cases, model_predictions) if model_predictions else None,
        "prediction_source_distribution": dict(Counter(str(item.get("prediction_source", "missing")) for item in logs.values())),
    }

    missing_model_logs = bool(logs) and not model_predictions
    if missing_model_logs:
        report["model_only_note"] = (
            "No model_prediction found in logs. Re-run Kaggle with the updated pipeline, then copy "
            "logs/prediction_logs.jsonl back here or run this script directly on Kaggle."
        )

    wrong_cases = []
    for case in gold_cases:
        case_id = str(case["case_id"])
        gold = map_label(str(case["verdict_label"]))
        pred = final_predictions.get(case_id) or log_final_predictions.get(case_id)
        if pred is None or pred == gold:
            continue
        log = logs.get(case_id)
        stats = evidence_stats(log, case)
        wrong_cases.append(
            {
                "case_id": case_id,
                "gold": gold,
                "pred": pred,
                "verdict_label": case.get("verdict_label"),
                "rule": prediction_from(log.get("rule_prediction")) if log else None,
                "model": prediction_from(log.get("model_prediction")) if log else None,
                "prediction_source": log.get("prediction_source") if log else None,
                **stats,
            }
        )
    report["wrong_cases"] = wrong_cases[: args.wrong_limit]

    if logs:
        stats_by_correctness = Counter()
        for case in gold_cases:
            case_id = str(case["case_id"])
            pred = final_predictions.get(case_id) or log_final_predictions.get(case_id)
            if pred is None:
                continue
            stats = evidence_stats(logs.get(case_id), case)
            key = "correct" if pred == map_label(str(case["verdict_label"])) else "wrong"
            if stats["has_decision_marker"]:
                stats_by_correctness[f"{key}_has_decision_marker"] += 1
            else:
                stats_by_correctness[f"{key}_missing_decision_marker"] += 1
        report["retrieval_marker_summary"] = dict(stats_by_correctness)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
