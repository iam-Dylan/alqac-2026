from __future__ import annotations

from pathlib import Path
from typing import Any

from .input_loader import load_cases
from .law_evidence import is_internal_law_evidence, is_public_law_evidence
from .law_retriever import load_law_keys
from .utils import read_json, write_json


VALID_LABELS = {"A_WIN", "B_WIN"}


def parse_law_evidence(value: str) -> tuple[str, int] | None:
    if "|" not in value:
        return None
    law_id, aid = value.rsplit("|", 1)
    law_id = law_id.strip()
    if not law_id:
        return None
    try:
        return law_id, int(aid)
    except ValueError:
        return None


def validate_submission_data(
    cases: list[Any],
    submission: Any,
    law_keys: set[tuple[str, int]] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(submission, list):
        return {"ok": False, "errors": ["Submission must be a JSON list"], "warnings": warnings}

    expected_ids = [case.case_id for case in cases]
    expected_set = set(expected_ids)
    seen_ids: set[str] = set()
    if len(submission) != len(cases):
        errors.append(f"Submission length {len(submission)} != input length {len(cases)}")

    for idx, item in enumerate(submission):
        if not isinstance(item, dict):
            errors.append(f"Item #{idx} must be an object")
            continue
        extra = set(item) - {"case_id", "prediction", "case_evidence", "law_evidence"}
        if extra:
            errors.append(f"Item #{idx} has extra fields: {sorted(extra)}")
        case_id = item.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            errors.append(f"Item #{idx} missing valid case_id")
        elif case_id in seen_ids:
            errors.append(f"Duplicate case_id in submission: {case_id}")
        else:
            seen_ids.add(case_id)
            if case_id not in expected_set:
                errors.append(f"Unexpected case_id: {case_id}")
        if item.get("prediction") not in VALID_LABELS:
            errors.append(f"Item #{idx} has invalid prediction: {item.get('prediction')!r}")
        case_evidence = item.get("case_evidence")
        if not isinstance(case_evidence, list) or not all(isinstance(x, str) for x in case_evidence):
            errors.append(f"Item #{idx} case_evidence must be list[str]")
        elif len(case_evidence) != len(set(case_evidence)):
            errors.append(f"Item #{idx} has duplicate case_evidence")
        law_evidence = item.get("law_evidence")
        if not isinstance(law_evidence, list):
            errors.append(f"Item #{idx} law_evidence must be a list")
        else:
            seen_law: set[tuple[str, int]] = set()
            for j, law in enumerate(law_evidence):
                if not isinstance(law, str):
                    errors.append(f"Item #{idx} law_evidence #{j} must be a string")
                    continue
                if is_public_law_evidence(law):
                    continue
                key = parse_law_evidence(law)
                if key is None:
                    errors.append(f"Item #{idx} law_evidence #{j} must use public 'law name | article' or internal 'law_id|aid' format")
                    continue
                if key in seen_law:
                    errors.append(f"Item #{idx} has duplicate law evidence {key}")
                seen_law.add(key)
                if law_keys is not None and key not in law_keys:
                    errors.append(f"Item #{idx} law evidence not in corpus: {key}")

    missing = expected_set - seen_ids
    if missing:
        errors.append(f"Missing case_ids: {sorted(missing)[:10]}")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def validate_submission_files(
    input_path: str | Path,
    submission_path: str | Path,
    law_corpus_path: str | Path | None = None,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    cases = load_cases(input_path)
    submission = read_json(submission_path)
    law_keys = load_law_keys(law_corpus_path) if law_corpus_path else None
    report = validate_submission_data(cases, submission, law_keys)
    if report_path:
        write_json(report_path, report)
    return report
