from __future__ import annotations

from typing import Any


DECISION_MARKERS = [
    "QUYẾT ĐỊNH",
    "Tuyên xử",
    "Chấp nhận yêu cầu",
    "Không chấp nhận yêu cầu",
    "Bác yêu cầu",
]

REASONING_MARKERS = [
    "Hội đồng xét xử nhận định",
    "Xét thấy",
    "Có căn cứ",
    "Không có căn cứ",
    "Căn cứ vào",
]

CLAIM_MARKERS = ["Nguyên đơn yêu cầu", "Bị đơn trình bày", "Không đồng ý", "Phản tố"]


def segment_roles(segment: dict[str, Any]) -> list[str]:
    text = str(segment.get("text", "")).lower()
    roles: list[str] = []
    if any(marker.lower() in text for marker in DECISION_MARKERS):
        roles.append("decision")
    if any(marker.lower() in text for marker in REASONING_MARKERS):
        roles.append("reasoning")
    if any(marker.lower() in text for marker in CLAIM_MARKERS):
        roles.append("claim_or_defense")
    return roles


def has_role(segments: list[dict[str, Any]], role: str) -> bool:
    return any(role in segment_roles(segment) for segment in segments)


def has_enough_core_evidence(segments: list[dict[str, Any]]) -> bool:
    return has_role(segments, "decision") and has_role(segments, "reasoning")


def score_segment(segment: dict[str, Any]) -> float:
    text = str(segment.get("text", ""))
    score = float(segment.get("score", 0) or 0)
    bonus = 0.0
    for marker in DECISION_MARKERS:
        if marker.lower() in text.lower():
            bonus += 5.0
    for marker in REASONING_MARKERS:
        if marker.lower() in text.lower():
            bonus += 3.0
    for marker in CLAIM_MARKERS:
        if marker.lower() in text.lower():
            bonus += 1.0
    if str(segment.get("query", "")).lower().startswith(("quyết định", "tuyên xử")):
        bonus += 1.0
    return score + bonus


def deduplicate_segments(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_chunk: dict[str, dict[str, Any]] = {}
    for item in items:
        chunk_id = str(item.get("chunk_id", ""))
        if not chunk_id:
            continue
        existing = by_chunk.get(chunk_id)
        if existing is None or score_segment(item) > score_segment(existing):
            enriched = dict(item)
            enriched["utility_score"] = score_segment(item)
            enriched["roles"] = segment_roles(item)
            by_chunk[chunk_id] = enriched
    return sorted(by_chunk.values(), key=lambda item: float(item.get("utility_score", 0)), reverse=True)
