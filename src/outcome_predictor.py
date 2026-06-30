from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .query_parser import ParsedQuery, parse_case_query
from .utils import tokenize


FINAL_DECISION_HINTS = [
    "quyết định",
    "tuyên xử",
    "xử:",
    "xử :",
    "cụ thể tuyên",
]

REASONING_HINTS = [
    "hội đồng xét xử nhận định",
    "xét thấy",
    "có căn cứ",
    "không có căn cứ",
    "nhận định",
]

POSITIVE_PATTERNS = [
    "chấp nhận toàn bộ yêu cầu",
    "chấp nhận yêu cầu khởi kiện",
    "chấp nhận yêu cầu",
    "chấp nhận một phần yêu cầu khởi kiện",
    "chấp nhận một phần yêu cầu",
    "có căn cứ chấp nhận",
    "buộc bị đơn",
]

NEGATIVE_PATTERNS = [
    "không chấp nhận yêu cầu khởi kiện",
    "không chấp nhận toàn bộ yêu cầu",
    "bác yêu cầu khởi kiện",
    "bác toàn bộ yêu cầu",
    "không có căn cứ chấp nhận",
]

SECONDARY_REJECTION_HINTS = [
    "phần yêu cầu",
    "phần còn lại",
    "yêu cầu còn lại",
    "không được tòa án chấp nhận",
    "không được chấp nhận",
]

DEFENSE_REJECTION_HINTS = [
    "bác yêu cầu phản tố",
    "không chấp nhận yêu cầu phản tố",
    "bác yêu cầu độc lập",
]


@dataclass(frozen=True)
class EvidenceSignal:
    polarity: str
    weight: float
    pattern: str
    chunk_id: str
    text_type: str


def _contains_any(text: str, patterns: list[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _text_type(text: str) -> str:
    lowered = text.lower()
    if _contains_any(lowered, FINAL_DECISION_HINTS):
        return "decision"
    if _contains_any(lowered, REASONING_HINTS):
        return "reasoning"
    return "other"


def _base_weight(text_type: str) -> float:
    if text_type == "decision":
        return 3.0
    if text_type == "reasoning":
        return 1.7
    return 1.0


def _main_claim_terms(parsed: ParsedQuery) -> set[str]:
    terms: set[str] = set()
    for phrase in (parsed.plaintiff_claim, parsed.legal_relation):
        terms.update(token for token in tokenize(phrase) if len(token) >= 4)
    return terms


def _claim_overlap_weight(text: str, parsed: ParsedQuery) -> float:
    terms = _main_claim_terms(parsed)
    if not terms:
        return 1.0
    text_terms = set(tokenize(text))
    overlap = len(terms & text_terms)
    if overlap >= 4:
        return 1.4
    if overlap >= 2:
        return 1.2
    return 0.9


def _party_weight(text: str, parsed: ParsedQuery, polarity: str) -> float:
    lowered = text.lower()
    plaintiff = parsed.plaintiff.lower() if parsed.plaintiff else ""
    defendant = parsed.defendant.lower() if parsed.defendant else ""
    if polarity == "positive" and plaintiff and plaintiff in lowered:
        return 1.15
    if polarity == "positive" and defendant and re.search(rf"buộc\s+.{0,80}{re.escape(defendant)}", lowered):
        return 1.25
    if polarity == "negative" and plaintiff and plaintiff in lowered:
        return 1.15
    return 1.0


def _is_negated_match(text: str, start: int) -> bool:
    prefix = text[max(0, start - 24):start]
    return bool(re.search(r"(không|chưa|bác)\s+$", prefix))


def _iter_unnegated_patterns(text: str, patterns: list[str]) -> list[str]:
    matched: list[str] = []
    for pattern in patterns:
        start = text.find(pattern)
        while start != -1:
            if not _is_negated_match(text, start):
                matched.append(pattern)
                break
            start = text.find(pattern, start + 1)
    return matched


def _has_positive_obligation(text: str, parsed: ParsedQuery) -> bool:
    defendant = re.escape(parsed.defendant.lower()) if parsed.defendant else ""
    plaintiff = re.escape(parsed.plaintiff.lower()) if parsed.plaintiff else ""
    patterns = [r"buộc\s+bị đơn", r"bị đơn\s+phải\s+(trả|thanh toán|bồi thường)"]
    if defendant:
        patterns.extend(
            [
                rf"buộc\s+.{{0,80}}{defendant}",
                rf"{defendant}.{{0,80}}phải\s+(trả|thanh toán|bồi thường)",
            ]
        )
    if plaintiff:
        patterns.extend(
            [
                rf"trả\s+cho\s+.{{0,80}}{plaintiff}",
                rf"bồi thường\s+.{{0,80}}cho\s+.{{0,80}}{plaintiff}",
            ]
        )
    return any(re.search(pattern, text) for pattern in patterns)


def _collect_signals(case_query: str, segments: list[dict[str, Any]], parsed: ParsedQuery) -> list[EvidenceSignal]:
    signals: list[EvidenceSignal] = []
    for segment in segments:
        text = str(segment.get("text", ""))
        lowered = text.lower()
        text_type = _text_type(lowered)
        base = _base_weight(text_type) * _claim_overlap_weight(lowered, parsed)
        chunk_id = str(segment.get("chunk_id", ""))

        secondary_rejection = _contains_any(lowered, SECONDARY_REJECTION_HINTS)
        for pattern in DEFENSE_REJECTION_HINTS:
            if pattern in lowered:
                signals.append(EvidenceSignal("positive", base * 1.4, pattern, chunk_id, text_type))
        for pattern in _iter_unnegated_patterns(lowered, POSITIVE_PATTERNS):
            weight = base * _party_weight(lowered, parsed, "positive")
            if "một phần" in pattern:
                weight *= 1.35
            signals.append(EvidenceSignal("positive", weight, pattern, chunk_id, text_type))
        if _has_positive_obligation(lowered, parsed):
            signals.append(EvidenceSignal("positive", base * 1.25, "defendant obligation to plaintiff", chunk_id, text_type))
        for pattern in NEGATIVE_PATTERNS:
            if pattern in lowered:
                weight = base * _party_weight(lowered, parsed, "negative")
                if secondary_rejection and any(sig.polarity == "positive" and sig.chunk_id == chunk_id for sig in signals):
                    weight *= 0.35
                signals.append(EvidenceSignal("negative", weight, pattern, chunk_id, text_type))
    return signals


def _summarize(signals: list[EvidenceSignal]) -> str:
    parts = []
    for signal in sorted(signals, key=lambda s: s.weight, reverse=True)[:6]:
        parts.append(f"{signal.polarity}:{signal.pattern}@{signal.text_type}:{signal.weight:.2f}")
    return "; ".join(parts)


def predict_outcome(
    case_query: str,
    segments: list[dict[str, Any]],
    parsed: ParsedQuery | None = None,
) -> dict[str, Any]:
    parsed = parsed or parse_case_query(case_query)
    signals = _collect_signals(case_query, segments, parsed)
    positive = sum(signal.weight for signal in signals if signal.polarity == "positive")
    negative = sum(signal.weight for signal in signals if signal.polarity == "negative")

    has_decision_positive = any(signal.polarity == "positive" and signal.text_type == "decision" for signal in signals)
    has_decision_negative = any(signal.polarity == "negative" and signal.text_type == "decision" for signal in signals)

    if has_decision_positive and positive >= negative * 0.85:
        confidence = 0.86 if positive > negative else 0.68
        return {
            "prediction": "A_WIN",
            "confidence": confidence,
            "rationale": f"Decision-level plaintiff win or partial win detected. Signals: {_summarize(signals)}",
        }
    if has_decision_negative and negative > positive * 1.15:
        return {
            "prediction": "B_WIN",
            "confidence": 0.82,
            "rationale": f"Decision-level rejection of main claim detected. Signals: {_summarize(signals)}",
        }
    if positive > negative:
        margin = positive - negative
        return {
            "prediction": "A_WIN",
            "confidence": min(0.82, 0.55 + margin / max(positive + negative, 1)),
            "rationale": f"Evidence-weighted plaintiff-favorable outcome. Signals: {_summarize(signals)}",
        }
    if negative > positive:
        margin = negative - positive
        return {
            "prediction": "B_WIN",
            "confidence": min(0.82, 0.55 + margin / max(positive + negative, 1)),
            "rationale": f"Evidence-weighted defendant-favorable outcome. Signals: {_summarize(signals)}",
        }
    return {
        "prediction": "A_WIN",
        "confidence": 0.35,
        "rationale": "No decisive accept/reject signal found; public prior fallback is A_WIN.",
    }
