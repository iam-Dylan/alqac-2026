from __future__ import annotations

import re
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class ParsedQuery:
    plaintiff: str = ""
    defendant: str = ""
    legal_relation: str = ""
    plaintiff_claim: str = ""
    dispute_type: str = "general"
    keywords: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["keywords"] = list(self.keywords)
        return data


def _extract_between(text: str, start_patterns: list[str], end_patterns: list[str]) -> str:
    start = None
    for pattern in start_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            start = match.end()
            break
    if start is None:
        return ""
    rest = text[start:]
    end = len(rest)
    for pattern in end_patterns:
        match = re.search(pattern, rest, flags=re.IGNORECASE)
        if match:
            end = min(end, match.start())
    return rest[:end].strip(" ,.;:")


def parse_case_query(case_query: str) -> ParsedQuery:
    plaintiff = _extract_between(
        case_query,
        [r"\bnguyên đơn\b", r"\bngười khởi kiện\b"],
        [r"\bbị đơn\b", r"\bvà\b", r"\bkhởi kiện\b", r"\btranh chấp\b"],
    )
    if not plaintiff:
        plaintiff_match = re.search(r"^(.{2,120}?)\s+khởi kiện\s+", case_query, flags=re.IGNORECASE)
        if plaintiff_match:
            plaintiff = plaintiff_match.group(1).strip(" ,.;:")
    defendant = _extract_between(
        case_query,
        [r"\bbị đơn\b", r"\bkhởi kiện\b"],
        [r"\bvề\b", r"\btranh chấp\b", r"\byêu cầu\b", r"\. Agent\b"],
    )

    relation_match = re.search(r"tranh chấp\s+(.+?)(?:\.|,| Agent| Nguyên đơn| Chị| Ông| Bà| Anh)", case_query)
    if not relation_match:
        relation_match = re.search(r"\bvề\s+(.+?)(?:\.|,| Agent| yêu cầu)", case_query, flags=re.IGNORECASE)
    legal_relation = relation_match.group(1).strip() if relation_match else ""
    claim_match = re.search(r"yêu cầu\s+(.+?)(?:\.| Agent|$)", case_query, flags=re.IGNORECASE)
    plaintiff_claim = claim_match.group(1).strip() if claim_match else ""

    keywords = []
    for phrase in (legal_relation, plaintiff_claim):
        for token in re.findall(r"[\wÀ-ỹ]{4,}", phrase.lower(), flags=re.UNICODE):
            if token not in keywords:
                keywords.append(token)

    return ParsedQuery(
        plaintiff=plaintiff,
        defendant=defendant,
        legal_relation=legal_relation,
        plaintiff_claim=plaintiff_claim,
        dispute_type=detect_dispute_type(case_query),
        keywords=tuple(keywords[:12]),
    )


def detect_dispute_type(case_query: str) -> str:
    text = case_query.lower()
    rules = [
        ("land", ["quyền sử dụng đất", "chuyển nhượng đất", "thửa đất", "sổ đỏ", "giấy chứng nhận quyền sử dụng"]),
        ("compensation", ["bồi thường", "thiệt hại", "ngoài hợp đồng", "tai nạn", "súc vật"]),
        ("contract", ["hợp đồng", "chuyển nhượng", "đặt cọc", "mua bán", "vay tài sản", "tín dụng"]),
        ("marriage_family", ["ly hôn", "hôn nhân", "nuôi con", "cấp dưỡng", "tài sản chung"]),
        ("inheritance", ["thừa kế", "di sản", "hàng thừa kế", "chia di sản"]),
        ("labor", ["lao động", "tiền lương", "sa thải", "bảo hiểm xã hội"]),
        ("administrative", ["quyết định hành chính", "khiếu kiện", "ủy ban nhân dân", "thu hồi đất"]),
        ("commercial", ["kinh doanh thương mại", "công ty", "cổ phần", "thành viên góp vốn"]),
    ]
    for dispute_type, markers in rules:
        if any(marker in text for marker in markers):
            return dispute_type
    return "general"
