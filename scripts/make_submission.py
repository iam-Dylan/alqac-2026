#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.evaluate_case_recall import evaluate as evaluate_case_recall
from scripts.evaluate_public import evaluate as evaluate_public
from src.pipeline import run_pipeline
from src.utils import load_config


def as_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    value = value.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected boolean value, got: {value}")


def dump_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(str(value), ensure_ascii=False)


def write_simple_yaml(path: str | Path, config: dict[str, Any]) -> None:
    lines: list[str] = []
    for section, values in config.items():
        lines.append(f"{section}:")
        if not isinstance(values, dict):
            lines.append(f"  value: {dump_scalar(values)}")
            continue
        for key, value in values.items():
            lines.append(f"  {key}: {dump_scalar(value)}")
        lines.append("")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def resolve_input(mode: str, explicit_input: str | None) -> str:
    if explicit_input:
        return explicit_input
    if mode == "private":
        return "data/private_test.json"
    return "data/ALQAC2026_public_test.json"


def build_runtime_config(args: argparse.Namespace) -> Path:
    config = load_config(args.config)

    config.setdefault("retrieval", {})
    config["retrieval"]["queries_per_case"] = args.queries_per_case
    config["retrieval"]["min_queries_per_case"] = args.min_queries_per_case
    config["retrieval"]["adaptive_stop"] = args.adaptive_stop
    config["retrieval"]["max_case_evidence"] = args.max_case_evidence

    config.setdefault("prediction", {})
    config["prediction"]["use_model_reasoner"] = bool(args.use_model)
    if not args.use_model:
        config["prediction"]["adapter_path"] = None
        config["prediction"]["load_in_4bit"] = False

    runtime_config = Path(args.runtime_config)
    write_simple_yaml(runtime_config, config)
    return runtime_config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create ALQAC submission.json in one command. Defaults to rule-only + recall-first retrieval."
    )
    parser.add_argument("--mode", choices=["public", "private"], default="public")
    parser.add_argument("--input", help="Input JSON. Defaults by --mode.")
    parser.add_argument("--law-corpus", default="data/corpus_law_pub.json")
    parser.add_argument("--output", default="outputs/submission.json")
    parser.add_argument("--config", default="configs/config.yaml")
    parser.add_argument("--runtime-config", default="outputs/run_submission_config.yaml")

    parser.add_argument("--use-model", action="store_true", help="Enable configured local model reasoner. Off by default.")
    parser.add_argument("--queries-per-case", type=int, default=20)
    parser.add_argument("--min-queries-per-case", type=int, default=12)
    parser.add_argument("--adaptive-stop", type=as_bool, default=False)
    parser.add_argument("--max-case-evidence", type=int, default=20)

    parser.add_argument("--skip-public-eval", action="store_true")
    parser.add_argument("--skip-case-recall-diagnostic", action="store_true")
    args = parser.parse_args()

    input_path = resolve_input(args.mode, args.input)
    runtime_config = build_runtime_config(args)

    result = run_pipeline(
        input_path=input_path,
        law_corpus_path=args.law_corpus,
        output_path=args.output,
        config_path=runtime_config,
    )
    print(f"Wrote {result['cases']} predictions -> {result['output']}")
    print(f"Runtime config -> {runtime_config}")

    if args.mode == "public" and not args.skip_public_eval:
        public_report = evaluate_public(input_path, args.output)
        print("Public outcome/law report:")
        print(json.dumps(public_report, ensure_ascii=False, indent=2))

    if not args.skip_case_recall_diagnostic:
        recall_report = evaluate_case_recall(
            input_path=input_path,
            submission_path=args.output,
            retrieval_log_path="logs/retrieval_logs.jsonl",
            cache_path="cache/case_api_cache.jsonl",
        )
        print("Case recall diagnostic:")
        print(json.dumps(recall_report, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
