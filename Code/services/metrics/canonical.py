"""Ánh xạ mã số in trên BCTC (theo mẫu) sang chỉ tiêu chuẩn dùng chung cho mọi mẫu.

Chỉ tiêu chuẩn giúp so sánh được giữa các năm (TT200 <-> TT99) và giữa các công ty. Chỉ khai báo các chỉ tiêu
đã thấy trên BCTC thực tế quý 2/2026; mã TT99 nào chưa chắc thì ghi chú. Ngân hàng dùng thẳng mã chuẩn b.* do
services/extraction/bank.py gán.
"""

from __future__ import annotations

# (báo cáo, chỉ tiêu chuẩn) -> mã số theo từng mẫu
CORPORATE: dict[tuple[str, str], dict[str, str]] = {
    ("IS", "revenue_gross"): {"TT200": "01", "TT99": "01"},
    ("IS", "revenue"): {"TT200": "10", "TT99": "10"},
    ("IS", "cogs"): {"TT200": "11", "TT99": "11"},
    ("IS", "gross_profit"): {"TT200": "20", "TT99": "20"},
    ("IS", "fin_income"): {"TT200": "21", "TT99": "22"},
    ("IS", "fin_expense"): {"TT200": "22", "TT99": "23"},
    ("IS", "interest_expense"): {"TT200": "23", "TT99": "24"},
    ("IS", "jv_profit"): {"TT200": "24", "TT99": "27"},       # TT99: theo BCTC FPT, MWG quý 2/2026
    ("IS", "selling_expense"): {"TT200": "25", "TT99": "25"},
    ("IS", "admin_expense"): {"TT200": "26", "TT99": "26"},
    ("IS", "operating_profit"): {"TT200": "30", "TT99": "30"},
    ("IS", "other_profit"): {"TT200": "40", "TT99": "40"},
    ("IS", "pbt"): {"TT200": "50", "TT99": "50"},
    ("IS", "npat"): {"TT200": "60", "TT99": "60"},
    ("IS", "npat_parent"): {"TT200": "61", "TT99": "61"},
    ("IS", "minority"): {"TT200": "62", "TT99": "62"},
    ("BS", "cash"): {"TT200": "110", "TT99": "110"},
    ("BS", "receivables"): {"TT200": "130", "TT99": "130"},  # phải thu ngắn hạn
    ("BS", "inventory"): {"TT200": "140", "TT99": "140"},
    ("BS", "total_assets"): {"TT200": "270", "TT99": "280"},   # TT99 in 270 thì xem detect_template/rules
    ("BS", "liabilities"): {"TT200": "300", "TT99": "300"},
    ("BS", "equity"): {"TT200": "400", "TT99": "400"},
    ("CF", "cfo"): {"TT200": "20", "TT99": "20"},
    ("CF", "cfi"): {"TT200": "30", "TT99": "30"},
    ("CF", "cff"): {"TT200": "40", "TT99": "40"},
}

BANK: dict[tuple[str, str], str] = {
    ("IS", "nii"): "b.nii",
    ("IS", "net_fee"): "b.nfee",
    ("IS", "toi"): "b.toi",
    ("IS", "opex"): "b.opex",
    ("IS", "ppop"): "b.ppop",
    ("IS", "provision"): "b.prov",
    ("IS", "other_profit"): "b.nother",
    ("IS", "pbt"): "b.pbt",
    ("IS", "npat"): "b.npat",
    ("IS", "npat_parent"): "b.npat_parent",
    ("IS", "minority"): "b.mi",
    ("BS", "loans"): "b.loans",
    ("BS", "customer_deposits"): "b.cust_dep",
    ("BS", "total_assets"): "b.ta",
    ("BS", "equity"): "b.te",
    ("CF", "cfo"): "b.cfo",
}


# Công ty chứng khoán: mẫu B02/B01/B03-CTCK (TT334), mã in trên BCTC
CTCK: dict[tuple[str, str], str] = {
    ("IS", "revenue"): "20",           # cộng doanh thu hoạt động
    ("IS", "opex"): "40",              # cộng chi phí hoạt động
    ("IS", "fin_income"): "50",
    ("IS", "fin_expense"): "60",
    ("IS", "admin_expense"): "62",     # chi phí quản lý công ty chứng khoán
    ("IS", "operating_profit"): "70",  # kết quả hoạt động
    ("IS", "other_profit"): "80",      # cộng kết quả hoạt động khác
    ("IS", "pbt"): "90",
    ("IS", "npat"): "200",
    ("IS", "npat_parent"): "201",      # LNST phân bổ cho chủ sở hữu
    ("IS", "minority"): "203",         # phân bổ cho cổ đông không kiểm soát (SSI)
    ("BS", "total_assets"): "270",
    ("BS", "equity"): "400",
    ("CF", "cfo"): "60",
}


def code_for(template: str, statement: str, metric: str) -> str | None:
    if template == "TCTD":
        return BANK.get((statement, metric))
    if template == "CTCK":
        return CTCK.get((statement, metric))
    return CORPORATE.get((statement, metric), {}).get(template)
