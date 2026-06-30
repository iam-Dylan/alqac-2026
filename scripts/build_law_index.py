#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.law_retriever import BM25LawRetriever


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase A BM25 law index cache.")
    parser.add_argument("--law-corpus", default="data/corpus_law_pub.json")
    parser.add_argument("--output-dir", default="cache/law_index")
    args = parser.parse_args()

    retriever = BM25LawRetriever.from_law_corpus(args.law_corpus)
    index_path = retriever.save_index(args.output_dir)
    print(f"Indexed {len(retriever.records)} law provisions -> {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
