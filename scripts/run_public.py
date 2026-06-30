#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.pipeline import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase A pipeline on public input.")
    parser.add_argument("--input", default="data/ALQAC2026_public_test.json")
    parser.add_argument("--law-corpus", default="data/corpus_law_pub.json")
    parser.add_argument("--output", default="outputs/public_submission.json")
    parser.add_argument("--config", default="configs/config.yaml")
    args = parser.parse_args()

    result = run_pipeline(args.input, args.law_corpus, args.output, args.config)
    print(f"Wrote {result['cases']} predictions -> {result['output']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
