"""Danh mục chỉ tiêu cho agent báo cáo: chỉ tiêu theo loại công ty (mã chuẩn của services/metrics/canonical.py), tên hiển
thị, các cách người đọc hay gọi, và tỷ lệ do code tính (tử / mẫu × 100)."""

from __future__ import annotations

from services.metrics.card import EXPENSE_METRICS, KEY_METRICS

KIND_OF_TEMPLATE = {"TT200": "corporate", "TT99": "corporate", "TCTD": "TCTD", "CTCK": "CTCK"}
KIND_OF_COMPANY = {"corporate": "corporate", "bank": "TCTD", "securities": "CTCK"}   # cột companies.template

METRICS: dict[str, dict[str, str]] = {
    "corporate": {"revenue": "Doanh thu thuần", "gross_profit": "Lợi nhuận gộp",
                  "fin_income": "Doanh thu hoạt động tài chính", "fin_expense": "Chi phí tài chính",
                  "selling_expense": "Chi phí bán hàng", "admin_expense": "Chi phí quản lý doanh nghiệp",
                  "pbt": "Lợi nhuận trước thuế", "npat": "Lợi nhuận sau thuế",
                  "npat_parent": "LNST của cổ đông công ty mẹ"},
    "TCTD": {"nii": "Thu nhập lãi thuần", "toi": "Tổng thu nhập hoạt động", "opex": "Chi phí hoạt động",
             "provision": "Chi phí dự phòng rủi ro tín dụng", "pbt": "Lợi nhuận trước thuế",
             "npat_parent": "LNST của cổ đông ngân hàng mẹ"},
    "CTCK": {"revenue": "Cộng doanh thu hoạt động", "opex": "Cộng chi phí hoạt động",
             "pbt": "Lợi nhuận kế toán trước thuế", "npat_parent": "LNST phân bổ cho chủ sở hữu"},
}
RATIOS: dict[str, dict[str, tuple[str, str, str]]] = {
    "corporate": {"gross_margin": ("Biên lợi nhuận gộp", "gross_profit", "revenue"),
                  "net_margin": ("Biên lợi nhuận ròng", "npat", "revenue")},
    "TCTD": {"cir": ("Chi phí hoạt động trên tổng thu nhập hoạt động", "opex", "toi")},
    "CTCK": {},
}
ALIASES = {
    "npat_parent": ["lnst", "lợi nhuận sau thuế", "lãi ròng", "lợi nhuận ròng", "lợi nhuận"],
    "npat": ["lnst", "lợi nhuận sau thuế"], "pbt": ["lntt", "lợi nhuận trước thuế"], "revenue": ["doanh thu"],
    "gross_profit": ["lợi nhuận gộp", "lãi gộp"], "nii": ["thu nhập lãi thuần", "thu nhập lãi"],
    "toi": ["tổng thu nhập hoạt động", "thu nhập hoạt động"], "opex": ["chi phí hoạt động"],
    "provision": ["dự phòng"], "fin_income": ["doanh thu tài chính"], "fin_expense": ["chi phí tài chính"],
    "selling_expense": ["chi phí bán hàng"], "admin_expense": ["chi phí quản lý"],
    "gross_margin": ["biên lợi nhuận gộp", "biên gộp"], "net_margin": ["biên lợi nhuận ròng", "biên ròng"],
    "cir": ["cir", "chi phí hoạt động trên"],
}
PROFIT = {"gross_profit", "pbt", "npat", "npat_parent"}
EXPENSES = set(EXPENSE_METRICS) | {"fin_expense"}
ALL_KEYS = sorted({k for m in METRICS.values() for k in m} | {k for r in RATIOS.values() for k in r})
SHARED = ["pbt", "npat_parent"]       # có ở mọi mẫu: dùng khi so các mã khác loại


def name(kind: str, key: str) -> str | None:
    if key in METRICS.get(kind, {}):
        return METRICS[kind][key]
    if key in RATIOS.get(kind, {}):
        return RATIOS[kind][key][0]
    return None


def names(kind: str, key: str) -> list[str]:
    own = name(kind, key)
    return ([own.lower()] if own else []) + ALIASES.get(key, [])


def keys_for(kind: str, metrics: list[str]) -> list[str]:
    """Chỉ tiêu cho một mã: các chỉ tiêu người dùng nêu mà mẫu của mã có; không nêu (hoặc không cái nào hợp) thì bộ của
    thẻ KQKD cộng các tỷ lệ của loại công ty đó."""
    valid = [k for k in metrics if name(kind, k)]
    return valid or [k for k, _ in KEY_METRICS[kind]] + list(RATIOS[kind])


def common_keys(kinds: set[str], metrics: list[str]) -> list[str]:
    """Chỉ tiêu dùng để so giữa các mã: cùng loại thì như keys_for; khác loại thì phần chung, mặc định LNTT và LNST."""
    if len(kinds) == 1:
        return keys_for(next(iter(kinds)), metrics)
    valid = [k for k in metrics if all(name(kd, k) for kd in kinds)]
    return valid or SHARED
