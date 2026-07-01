from __future__ import annotations

from pathlib import Path
from typing import Any

from .case_api_client import CaseAPIClient
from .evidence_selector import select_case_evidence
from .evidence_store import deduplicate_segments, has_enough_core_evidence
from .input_loader import CaseInput, load_cases
from .law_retriever import build_law_retriever, load_law_keys
from .law_evidence import law_hits_to_internal_strings, split_public_law_provisions
from .model_reasoner import LocalLLMReasoner, ModelReasonerUnavailable
from .outcome_predictor import predict_outcome
from .query_parser import parse_case_query
from .query_planner import plan_queries
from .submission_builder import build_submission_item
from .utils import append_jsonl, get_api_key, load_config, write_json
from .validator import validate_submission_data


DEFAULT_MODEL_OVERRIDE_MIN_CONFIDENCE = 0.80
DEFAULT_RULE_OVERRIDE_MAX_CONFIDENCE = 0.55


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def choose_prediction(
    rule_prediction: dict[str, Any],
    model_prediction: dict[str, Any],
    model_override_min_confidence: float = DEFAULT_MODEL_OVERRIDE_MIN_CONFIDENCE,
    rule_override_max_confidence: float = DEFAULT_RULE_OVERRIDE_MAX_CONFIDENCE,
) -> dict[str, Any]:
    rule_confidence = float(rule_prediction.get("confidence", 0.0))
    model_confidence = float(model_prediction.get("confidence", 0.0))
    if model_prediction["prediction"] == rule_prediction["prediction"]:
        prediction = dict(rule_prediction)
        prediction["confidence"] = max(rule_confidence, model_confidence)
        prediction["rationale"] = (
            "RULE_WITH_MODEL_AGREEMENT: "
            + str(rule_prediction.get("rationale", ""))
            + " MODEL: "
            + str(model_prediction.get("rationale", ""))
        )
        return prediction
    if rule_confidence <= rule_override_max_confidence and model_confidence >= model_override_min_confidence:
        prediction = dict(model_prediction)
        prediction["rationale"] = "MODEL_OVERRIDE_LOW_RULE_CONFIDENCE: " + str(prediction.get("rationale", ""))
        return prediction
    prediction = dict(rule_prediction)
    prediction["rationale"] = (
        "RULE_FALLBACK_MODEL_DISAGREEMENT: "
        + str(rule_prediction.get("rationale", ""))
        + " MODEL_WAS: "
        + str(model_prediction.get("prediction"))
        + f"({model_confidence:.2f}) "
        + str(model_prediction.get("rationale", ""))
    )
    return prediction


def build_client(config: dict[str, Any]) -> CaseAPIClient:
    api_cfg = config["api"]
    cache_dir = Path(config["paths"]["cache_dir"])
    return CaseAPIClient(
        base_url=str(api_cfg["base_url"]),
        endpoint=str(api_cfg["endpoint"]),
        api_key=get_api_key(config),
        cache_path=cache_dir / "case_api_cache.jsonl",
        min_interval_seconds=float(api_cfg["min_interval_seconds"]),
        timeout_seconds=float(api_cfg["timeout_seconds"]),
        max_retries=int(api_cfg["max_retries"]),
        ssl_verify=_as_bool(api_cfg.get("ssl_verify"), default=False),
    )


def retrieve_case_segments(
    case: CaseInput,
    queries: list[str],
    client: CaseAPIClient,
    min_queries: int = 0,
    adaptive_stop: bool = False,
) -> tuple[list[dict[str, Any]], int, int]:
    before = client.api_call_count
    segments: list[dict[str, Any]] = []
    executed = 0
    for idx, query in enumerate(queries):
        executed += 1
        response = client.retrieve(case.case_id, query)
        results = response.get("results", [])
        if not results:
            continue
        result = dict(results[0])
        result["query"] = query
        result["cached"] = bool(response.get("_cached", False))
        segments.append(result)
        deduped = deduplicate_segments(segments)
        if adaptive_stop and idx + 1 >= min_queries and has_enough_core_evidence(deduped):
            return deduped, client.api_call_count - before, executed
    return deduplicate_segments(segments), client.api_call_count - before, executed


def run_pipeline(
    input_path: str | Path,
    law_corpus_path: str | Path,
    output_path: str | Path,
    config_path: str | Path = "configs/config.yaml",
) -> dict[str, Any]:
    config = load_config(config_path)
    cases = load_cases(input_path)
    client = build_client(config)
    law_retriever = build_law_retriever(config, law_corpus_path)
    prediction_cfg = config.get("prediction", {})
    model_reasoner = None
    if _as_bool(prediction_cfg.get("use_model_reasoner"), default=False):
        try:
            model_reasoner = LocalLLMReasoner(
                model_name=str(prediction_cfg.get("model_name", "Qwen/Qwen2.5-7B-Instruct")),
                max_input_chars=int(prediction_cfg.get("max_input_chars", 12000)),
                max_new_tokens=int(prediction_cfg.get("max_new_tokens", 256)),
                adapter_path=prediction_cfg.get("adapter_path"),
            )
        except ModelReasonerUnavailable:
            raise

    retrieval_cfg = config["retrieval"]
    law_cfg = config["law_retrieval"]
    logs_dir = Path(config["paths"]["logs_dir"])
    retrieval_log_path = logs_dir / "retrieval_logs.jsonl"
    prediction_log_path = logs_dir / "prediction_logs.jsonl"
    submission: list[dict[str, Any]] = []

    for case in cases:
        parsed = parse_case_query(case.case_query)
        queries = plan_queries(case, parsed, int(retrieval_cfg["queries_per_case"]))
        segments, api_calls, queries_executed = retrieve_case_segments(
            case,
            queries,
            client,
            min_queries=int(retrieval_cfg.get("min_queries_per_case", 0)),
            adaptive_stop=_as_bool(retrieval_cfg.get("adaptive_stop"), default=True),
        )
        selected_case_evidence = select_case_evidence(segments, int(retrieval_cfg["max_case_evidence"]))
        law_query = " ".join([case.case_query] + [str(s.get("text", ""))[:800] for s in segments[:3]])
        law_hits = law_retriever.search(law_query, int(law_cfg["top_k"]))
        public_law_evidence: list[str] = []
        if hasattr(case, "raw") and isinstance(case.raw, dict):
            public_law_evidence = split_public_law_provisions(str(case.raw.get("related_law_provisions", "")))
        rule_prediction = predict_outcome(case.case_query, segments, parsed)
        prediction = rule_prediction
        if model_reasoner is not None:
            try:
                model_prediction = model_reasoner.predict(
                    case.case_query,
                    parsed,
                    segments,
                    public_law_evidence or law_hits_to_internal_strings(law_hits),
                )
                prediction = choose_prediction(
                    rule_prediction,
                    model_prediction,
                    model_override_min_confidence=float(
                        prediction_cfg.get("model_override_min_confidence", DEFAULT_MODEL_OVERRIDE_MIN_CONFIDENCE)
                    ),
                    rule_override_max_confidence=float(
                        prediction_cfg.get("rule_override_max_confidence", DEFAULT_RULE_OVERRIDE_MAX_CONFIDENCE)
                    ),
                )
            except Exception as exc:
                prediction = rule_prediction
                prediction["rationale"] = f"RULE_FALLBACK_MODEL_ERROR({type(exc).__name__}): {prediction['rationale']}"
        item = build_submission_item(
            case_id=case.case_id,
            prediction=prediction["prediction"],
            case_evidence=selected_case_evidence,
            law_evidence=public_law_evidence or law_hits,
        )
        submission.append(item)

        log_item = {
            "case_id": case.case_id,
            "case_query": case.case_query,
            "parsed": parsed.to_dict(),
            "queries": queries,
            "queries_executed": queries_executed,
            "retrieved_segments": segments,
            "selected_case_evidence": selected_case_evidence,
            "law_evidence": item["law_evidence"],
            "prediction": prediction["prediction"],
            "confidence": prediction["confidence"],
            "reasoning_summary": prediction["rationale"],
            "api_call_count": api_calls,
        }
        append_jsonl(retrieval_log_path, log_item)
        append_jsonl(prediction_log_path, log_item)

    report = validate_submission_data(cases, submission, load_law_keys(law_corpus_path))
    report_path = Path(config["paths"]["logs_dir"]) / "validation_report.json"
    write_json(report_path, report)
    if not report["ok"]:
        raise RuntimeError(f"Submission validation failed; see {report_path}: {report['errors'][:5]}")

    write_json(output_path, submission)
    return {"output": str(output_path), "validation": report, "cases": len(cases)}
