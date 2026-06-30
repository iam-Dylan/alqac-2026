from __future__ import annotations

import re
from typing import Any


def format_internal_law_evidence(law_id: str, aid: int) -> str:
    return f"{law_id}|{aid}"


def normalize_public_law_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    text = re.sub(r"\s*\|\s*", " | ", text)
    text = re.sub(r"\b[Kk]hoản\s+(\d+)\s+[Đđ]iều\s+(\d+)", r"Khoản \1 Điều \2", text)
    text = re.sub(r"\b[Đđ]iểm\s+([a-zA-Z])\s+[Kk]hoản\s+(\d+)\s+[Đđ]iều\s+(\d+)", r"Điểm \1 Khoản \2 Điều \3", text)
    text = re.sub(r"\b[Đđ]iều\s+(\d+)", r"Điều \1", text)
    return text


def split_public_law_provisions(value: str) -> list[str]:
    evidence: list[str] = []
    seen: set[str] = set()
    for raw_line in (value or "").splitlines():
        line = normalize_public_law_text(raw_line)
        if not line or "|" not in line:
            continue
        if line not in seen:
            seen.add(line)
            evidence.append(line)
    return evidence


def is_internal_law_evidence(value: str) -> bool:
    return bool(re.match(r"^.+\|\d+$", value or ""))


def is_public_law_evidence(value: str) -> bool:
    return bool(value and "|" in value and not is_internal_law_evidence(value))


def compact_law_evidence(values: list[str]) -> list[str]:
    compact: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_public_law_text(value) if is_public_law_evidence(value) else value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            compact.append(normalized)
    return compact


def law_hits_to_internal_strings(law_evidence: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for item in law_evidence:
        values.append(format_internal_law_evidence(str(item["law_id"]), int(item["aid"])))
    return compact_law_evidence(values)
