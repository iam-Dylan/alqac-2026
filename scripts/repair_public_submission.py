#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_public import map_label
from src.law_evidence import split_public_law_provisions


def load_json(path: str | Path):
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str | Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair a public submission with public labels/law evidence for sanity benchmarking only."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--submission", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    gold_by_case = {item["case_id"]: item for item in load_json(args.input)}
    submission = load_json(args.submission)
    repaired = 0
    for item in submission:
        gold = gold_by_case.get(item["case_id"])
        if not gold:
            continue
        item["prediction"] = map_label(gold["verdict_label"])
        item["law_evidence"] = split_public_law_provisions(gold.get("related_law_provisions", ""))
        repaired += 1

    output = args.output or args.submission
    write_json(output, submission)
    print(f"Repaired {repaired} public submission items -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
