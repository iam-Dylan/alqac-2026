#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_SOURCE_FIELDS = {
    "name",
    "category",
    "url_or_path",
    "access_date",
    "license_or_terms_note",
    "contains_labels",
    "intended_use",
}


def load_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_registry(path: str | Path) -> dict[str, Any]:
    registry = load_json(path)
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(registry, dict):
        return {"ok": False, "errors": ["Registry must be a JSON object"], "warnings": warnings}

    policy = registry.get("policy", {})
    allowed = set(policy.get("allowed_categories", []))
    prohibited = set(policy.get("prohibited_categories", []))
    sources = registry.get("sources", [])

    if not allowed:
        errors.append("policy.allowed_categories must not be empty")
    if not prohibited:
        errors.append("policy.prohibited_categories must not be empty")
    if not isinstance(sources, list):
        errors.append("sources must be a list")
        sources = []

    for idx, source in enumerate(sources):
        if not isinstance(source, dict):
            errors.append(f"source #{idx} must be an object")
            continue
        missing = REQUIRED_SOURCE_FIELDS - set(source)
        if missing:
            errors.append(f"source #{idx} missing fields: {sorted(missing)}")
        category = str(source.get("category", "")).strip()
        if category in prohibited:
            errors.append(f"source #{idx} uses prohibited category: {category}")
        if category not in allowed:
            errors.append(f"source #{idx} category is not in allowlist: {category!r}")
        if source.get("contains_labels") is True:
            errors.append(f"source #{idx} contains labels and is not allowed for this pipeline")
        intended_use = str(source.get("intended_use", "")).lower()
        if any(term in intended_use for term in ["train label", "supervised label", "outcome label"]):
            errors.append(f"source #{idx} intended_use suggests prohibited label training")
        url_or_path = str(source.get("url_or_path", "")).strip()
        if url_or_path and not (url_or_path.startswith(("http://", "https://")) or Path(url_or_path).exists()):
            warnings.append(f"source #{idx} local path does not exist yet: {url_or_path}")

    return {"ok": not errors, "errors": errors, "warnings": warnings, "sources": len(sources)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ALQAC external-source compliance registry.")
    parser.add_argument("--registry", default="data/external_sources.json")
    args = parser.parse_args()

    report = validate_registry(args.registry)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
