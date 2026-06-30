from __future__ import annotations

from typing import Any

from .law_evidence import compact_law_evidence, law_hits_to_internal_strings


def build_submission_item(
    case_id: str,
    prediction: str,
    case_evidence: list[str],
    law_evidence: list[dict[str, Any]] | list[str],
) -> dict[str, Any]:
    if law_evidence and isinstance(law_evidence[0], dict):
        compact_law = law_hits_to_internal_strings(law_evidence)  # type: ignore[arg-type]
    else:
        compact_law = compact_law_evidence([str(item) for item in law_evidence])
    return {
        "case_id": case_id,
        "prediction": prediction,
        "case_evidence": list(dict.fromkeys(case_evidence)),
        "law_evidence": compact_law,
    }
