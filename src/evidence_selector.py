from __future__ import annotations

from typing import Any

from .evidence_store import deduplicate_segments


def select_case_evidence(segments: list[dict[str, Any]], max_items: int = 8) -> list[str]:
    selected: list[str] = []
    for segment in deduplicate_segments(segments):
        chunk_id = str(segment.get("chunk_id", ""))
        if chunk_id and chunk_id not in selected:
            selected.append(chunk_id)
        if len(selected) >= max_items:
            break
    return selected
