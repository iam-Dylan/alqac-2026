#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.utils import normalize_space


GOLD_EVIDENCE_FIELDS = (
    "case_evidence",
    "gold_case_evidence",
    "relevant_case_evidence",
    "case_evidence_ids",
    "evidence",
)

TOTAL_CHUNK_FIELDS = (
    "num_chunks",
    "n_chunks",
    "total_chunks",
    "case_segment_count",
    "segment_count",
)

CORE_MARKERS = (
    "quyết định",
    "tuyên xử",
    "vì các lẽ trên",
    "hội đồng xét xử nhận định",
    "xét thấy",
    "chấp nhận yêu cầu",
    "không chấp nhận yêu cầu",
    "bác yêu cầu",
)


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def load_latest_jsonl(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    latest: dict[str, dict[str, Any]] = {}
    path = Path(path)
    if not path.exists():
        return latest
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            case_id = str(item.get("case_id", ""))
            if case_id:
                latest[case_id] = item
    return latest


def load_cache_counts(path: str | Path | None) -> dict[str, int]:
    if not path:
        return {}
    path = Path(path)
    queries_by_case: dict[str, set[str]] = defaultdict(set)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            case_id = str(item.get("case_id", ""))
            query = normalize_space(str(item.get("query", ""))).lower()
            if case_id and query:
                queries_by_case[case_id].add(query)
    return {case_id: len(queries) for case_id, queries in queries_by_case.items()}


def evidence_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    out: set[str] = set()
    for item in value:
        if isinstance(item, str):
            out.add(item)
        elif isinstance(item, dict):
            chunk_id = item.get("chunk_id") or item.get("id")
            if chunk_id:
                out.add(str(chunk_id))
    return out


def gold_evidence(case: dict[str, Any]) -> set[str]:
    for field in GOLD_EVIDENCE_FIELDS:
        values = evidence_set(case.get(field))
        if values:
            return values
    return set()


def max_seen_chunk_index(case: dict[str, Any], known_ids: set[str]) -> int | None:
    max_idx = -1
    prefix = f"{case.get('case_id')}_chunk_"
    for chunk_id in known_ids:
        if chunk_id.startswith(prefix):
            match = re.search(r"_chunk_(\d+)$", chunk_id)
            if match:
                max_idx = max(max_idx, int(match.group(1)))
    return max_idx if max_idx >= 0 else None


def total_chunks(case: dict[str, Any]) -> int | None:
    for field in TOTAL_CHUNK_FIELDS:
        value = case.get(field)
        if isinstance(value, int) and value > 0:
            return value
    return None


def efficiency_factor(api_calls: int | None, n_chunks: int | None) -> float | None:
    if api_calls is None or n_chunks is None or n_chunks <= 0:
        return None
    return max(0.0, 1.0 - max(0, api_calls - 2 * n_chunks) / (3 * n_chunks))


def text_hits(texts: list[str], target: str) -> int:
    target_norm = normalize_space(target).lower()
    if not target_norm:
        return 0
    hits = 0
    for text in texts:
        text_norm = normalize_space(text).lower()
        if text_norm and text_norm[:120] in target_norm:
            hits += 1
    return hits


def marker_hit(texts: list[str]) -> bool:
    joined = "\n".join(texts).lower()
    return any(marker in joined for marker in CORE_MARKERS)


def evaluate(
    input_path: str | Path,
    submission_path: str | Path,
    retrieval_log_path: str | Path | None,
    cache_path: str | Path | None,
) -> dict[str, Any]:
    cases = load_json(input_path)
    submissions = {str(item["case_id"]): item for item in load_json(submission_path)}
    logs = load_latest_jsonl(retrieval_log_path)
    cache_counts = load_cache_counts(cache_path)

    rows: list[dict[str, Any]] = []
    official_values: list[float] = []
    proxy = Counter()
    selected_counts: list[int] = []
    submitted_counts: list[int] = []
    api_call_counts: list[int] = []

    for case in cases:
        case_id = str(case["case_id"])
        submission = submissions.get(case_id, {})
        submitted = evidence_set(submission.get("case_evidence"))
        log = logs.get(case_id, {})
        retrieved_segments = log.get("retrieved_segments", [])
        selected_ids = evidence_set(log.get("selected_case_evidence")) or submitted
        known_ids = submitted | selected_ids | {
            str(segment.get("chunk_id", "")) for segment in retrieved_segments if segment.get("chunk_id")
        }

        gold = gold_evidence(case)
        n_chunks = total_chunks(case)
        max_seen_index = max_seen_chunk_index(case, known_ids)
        api_calls = log.get("api_calls")
        if api_calls is None:
            api_calls = log.get("queries_executed")
        if api_calls is None and isinstance(log.get("queries"), list):
            api_calls = len(log["queries"])
        if api_calls is None:
            api_calls = cache_counts.get(case_id)
        api_calls = int(api_calls) if isinstance(api_calls, int | float) else None

        eff = efficiency_factor(api_calls, n_chunks)
        official_recall = None
        penalized = None
        if gold:
            official_recall = len(submitted & gold) / len(gold)
            penalized = official_recall * (eff if eff is not None else 1.0)
            official_values.append(penalized)

        selected_texts = [
            str(segment.get("text", ""))
            for segment in retrieved_segments
            if str(segment.get("chunk_id", "")) in selected_ids
        ]
        has_marker = marker_hit(selected_texts)
        verdict_hits = text_hits(selected_texts, str(case.get("court_verdict", "")))
        reasoning_hits = text_hits(selected_texts, str(case.get("court_reasoning", "")))

        if has_marker:
            proxy["cases_with_core_marker"] += 1
        if verdict_hits:
            proxy["cases_with_verdict_text_hit"] += 1
        if reasoning_hits:
            proxy["cases_with_reasoning_text_hit"] += 1
        selected_counts.append(len(selected_ids))
        submitted_counts.append(len(submitted))
        if api_calls is not None:
            api_call_counts.append(api_calls)

        rows.append(
            {
                "case_id": case_id,
                "submitted_chunks": len(submitted),
                "selected_chunks": len(selected_ids),
                "retrieved_chunks": len(retrieved_segments),
                "api_calls_or_cached_queries": api_calls,
                "official_total_chunks": n_chunks,
                "max_seen_chunk_index": max_seen_index,
                "efficiency_factor": eff,
                "gold_chunks_available": bool(gold),
                "case_recall": official_recall,
                "penalized_case_recall": penalized,
                "has_core_marker_in_selected_text": has_marker,
                "verdict_text_hits": verdict_hits,
                "reasoning_text_hits": reasoning_hits,
            }
        )

    avg = lambda values: sum(values) / len(values) if values else 0.0
    report = {
        "cases": len(cases),
        "official_gold_case_evidence_available": any(row["gold_chunks_available"] for row in rows),
        "penalized_case_recall": avg(official_values) if official_values else None,
        "proxy_notice": (
            "Public file has no gold chunk IDs, so marker/text-hit metrics are diagnostics only."
            if not official_values
            else "Gold chunk IDs found; penalized_case_recall was computed."
        ),
        "avg_submitted_chunks": avg(submitted_counts),
        "avg_selected_chunks": avg(selected_counts),
        "avg_api_calls_or_cached_queries": avg(api_call_counts),
        "cases_with_core_marker_in_selected_text": proxy["cases_with_core_marker"],
        "cases_with_verdict_text_hit": proxy["cases_with_verdict_text_hit"],
        "cases_with_reasoning_text_hit": proxy["cases_with_reasoning_text_hit"],
        "low_coverage_cases": sorted(
            rows,
            key=lambda row: (
                row["has_core_marker_in_selected_text"],
                row["verdict_text_hits"] + row["reasoning_text_hits"],
                row["submitted_chunks"],
            ),
        )[:10],
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate or diagnose ALQAC case evidence recall.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--submission", required=True)
    parser.add_argument("--retrieval-log", default="logs/retrieval_logs.jsonl")
    parser.add_argument("--cache", default="cache/case_api_cache.jsonl")
    args = parser.parse_args()

    report = evaluate(args.input, args.submission, args.retrieval_log, args.cache)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
