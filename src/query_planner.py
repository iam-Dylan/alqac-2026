from __future__ import annotations

from .input_loader import CaseInput
from .query_parser import ParsedQuery
from .utils import normalize_space


DEFAULT_MARKER_QUERIES = [
    "Quyết định",
    "Tuyên xử",
    "Vì các lẽ trên",
    "Hội đồng xét xử nhận định",
    "Xét thấy",
    "Chấp nhận yêu cầu khởi kiện",
    "Không chấp nhận yêu cầu khởi kiện",
    "Bác yêu cầu khởi kiện",
    "Căn cứ",
    "Căn cứ vào các điều",
]

DISPUTE_TYPE_QUERIES = {
    "land": [
        "hợp đồng chuyển nhượng quyền sử dụng đất có hiệu lực",
        "giấy chứng nhận quyền sử dụng đất thửa đất",
        "công nhận hợp đồng chuyển nhượng quyền sử dụng đất",
    ],
    "contract": [
        "hợp đồng có hiệu lực nghĩa vụ thanh toán",
        "vi phạm nghĩa vụ hợp đồng",
        "buộc thực hiện hợp đồng",
    ],
    "compensation": [
        "bồi thường thiệt hại ngoài hợp đồng có căn cứ",
        "thiệt hại thực tế lỗi quan hệ nhân quả",
        "trách nhiệm bồi thường thiệt hại",
    ],
    "marriage_family": [
        "giao con cho nuôi dưỡng",
        "chia tài sản chung vợ chồng",
        "nghĩa vụ cấp dưỡng",
    ],
    "inheritance": [
        "chia di sản thừa kế",
        "hàng thừa kế quyền hưởng di sản",
        "di chúc hợp pháp",
    ],
    "labor": [
        "đơn phương chấm dứt hợp đồng lao động",
        "bồi thường do chấm dứt hợp đồng lao động",
        "tiền lương bảo hiểm xã hội",
    ],
    "administrative": [
        "hủy quyết định hành chính",
        "quyết định hành chính đúng pháp luật",
        "thu hồi đất bồi thường hỗ trợ tái định cư",
    ],
    "commercial": [
        "nghĩa vụ thanh toán kinh doanh thương mại",
        "tranh chấp thành viên công ty",
        "hợp đồng thương mại vi phạm nghĩa vụ",
    ],
}


def _party_queries(parsed: ParsedQuery) -> list[str]:
    queries = []
    if parsed.plaintiff:
        queries.extend(
            [
                f"{parsed.plaintiff} yêu cầu khởi kiện",
                f"Chấp nhận yêu cầu khởi kiện của {parsed.plaintiff}",
                f"Không chấp nhận yêu cầu khởi kiện của {parsed.plaintiff}",
            ]
        )
    if parsed.defendant:
        queries.extend(
            [
                f"{parsed.defendant} không đồng ý",
                f"buộc {parsed.defendant}",
            ]
        )
    return queries


def plan_queries(case: CaseInput, parsed: ParsedQuery, max_queries: int = 12) -> list[str]:
    candidates = [
        case.case_query,
        "Quyết định",
        "Tuyên xử",
        "Vì các lẽ trên",
        "Hội đồng xét xử nhận định",
        "Xét thấy",
        f"{parsed.legal_relation} {parsed.plaintiff_claim}",
        f"{parsed.plaintiff} yêu cầu {parsed.plaintiff_claim}",
        f"{parsed.defendant} không đồng ý {parsed.legal_relation}",
        f"nhận định {parsed.legal_relation} {parsed.plaintiff_claim}",
        f"quyết định {parsed.plaintiff_claim}",
    ]
    candidates.extend(_party_queries(parsed))
    candidates.extend(f"{marker} {parsed.legal_relation or parsed.plaintiff_claim or case.case_query}" for marker in DEFAULT_MARKER_QUERIES)
    candidates.extend(DISPUTE_TYPE_QUERIES.get(parsed.dispute_type, []))
    candidates.extend(
        [
            f"có căn cứ chấp nhận {parsed.plaintiff_claim or parsed.legal_relation}",
            f"không có căn cứ chấp nhận {parsed.plaintiff_claim or parsed.legal_relation}",
            f"yêu cầu của nguyên đơn {parsed.legal_relation}",
            f"ý kiến của bị đơn {parsed.legal_relation}",
        ]
    )

    queries: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        query = normalize_space(candidate)
        if not query:
            continue
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append(query)
        if len(queries) >= max_queries:
            break
    return queries
