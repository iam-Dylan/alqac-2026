#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.validator import validate_submission_files


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an ALQAC submission file.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--submission", required=True)
    parser.add_argument("--law-corpus", default=None)
    parser.add_argument("--report", default="logs/validation_report.json")
    args = parser.parse_args()

    report = validate_submission_files(args.input, args.submission, args.law_corpus, args.report)
    if report["ok"]:
        print(f"Validation passed -> {args.report}")
        return 0
    print(f"Validation failed -> {args.report}")
    for error in report["errors"][:20]:
        print(f"- {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
