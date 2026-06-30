from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .utils import read_json, normalize_space


@dataclass(frozen=True)
class CaseInput:
    case_id: str
    case_query: str
    raw: dict[str, Any] | None = None


def load_cases(path: str | Path) -> list[CaseInput]:
    data = read_json(path)
    if not isinstance(data, list):
        raise ValueError(f"Input must be a JSON list: {path}")

    cases: list[CaseInput] = []
    seen: set[str] = set()
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Input item #{idx} must be an object")
        case_id = normalize_space(str(item.get("case_id", "")))
        case_query = normalize_space(str(item.get("case_query", "")))
        if not case_id:
            raise ValueError(f"Input item #{idx} missing case_id")
        if not case_query:
            raise ValueError(f"Input item #{idx} missing case_query")
        if case_id in seen:
            raise ValueError(f"Duplicate case_id in input: {case_id}")
        seen.add(case_id)
        cases.append(CaseInput(case_id=case_id, case_query=case_query, raw=item))
    return cases


def records_to_cases(records: list[dict[str, Any]]) -> list[CaseInput]:
    return [
        CaseInput(case_id=normalize_space(str(r["case_id"])), case_query=normalize_space(str(r["case_query"])), raw=r)
        for r in records
    ]
