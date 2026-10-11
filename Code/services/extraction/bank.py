"""Gán mã chuẩn cho BCTC ngân hàng (mẫu TCTD theo TT49/2014/TT-NHNN, sửa bởi TT27/2021).

BCTC ngân hàng không in cột mã số như doanh nghiệp thường; số thứ tự đầu dòng (I, 1, a) cũng không nhất quán giữa
các ngân hàng (TCB không in số thứ tự). Vì vậy ánh xạ theo tên chỉ tiêu, viết theo cách gọi thực tế của VCB, TCB, ACB
quý 2/2026, rồi kiểm tra ràng buộc trên mã chuẩn (services/extraction/rules.py, bộ TCTD).

Quy tắc gán: với mỗi mã chuẩn, thử lần lượt các mẫu tên theo thứ tự ưu tiên; dòng đầu tiên khớp và có số thì nhận mã.
Dòng cha thường đứng trước dòng con cùng tên (ví dụ "Cho vay khách hàng" hai lần), nên lấy dòng đầu tiên là dòng cha.
"""

from __future__ import annotations

import re
import unicodedata

from services.extraction.validate import ExtractedStatement

# (mã chuẩn, [mẫu tên theo thứ tự ưu tiên]); mẫu dùng re.search trên tên đã làm sạch (_clean)
_PATTERNS: dict[str, list[tuple[str, list[str]]]] = {
    "BS": [
        # Tài sản: các mục cấp La Mã
        ("b.cash", [r"^tiền mặt(, vàng( bạc, đá quý)?)?$"]),
        ("b.sbv", [r"^tiền gửi tại (ngân hàng nhà nước|ngân hàng trung ương|nhnn)( việt nam)?( nhnn| nhnnvn)?$"]),
        ("b.interbank", [r"^tiền(, vàng)? gửi (tại )?và (cho vay|cấp tín dụng cho) (các )?(tổ chức tín dụng|tctd)( tctd)? khác( tctd)?$"]),
        ("b.trading_sec", [r"^chứng khoán kinh doanh$"]),
        ("b.deriv_asset", [r"^các công cụ tài chính phái sinh và các tài sản tài chính khác$"]),
        ("b.loans", [r"^cho vay khách hàng$"]),
        ("b.debt_purchase", [r"^hoạt động mua nợ$"]),
        ("b.inv_sec", [r"^chứng khoán đầu tư$"]),
        ("b.lt_invest", [r"^góp vốn, đầu tư dài hạn$"]),
        ("b.fixed_assets", [r"^tài sản cố định$"]),
        ("b.inv_property", [r"^bất động sản đầu tư$"]),
        ("b.other_assets", [r"^tài sản có khác$"]),
        ("b.ta", [r"^tổng (cộng )?tài sản( có)?$"]),
        # Nợ phải trả
        ("b.gov", [r"^các khoản nợ chính phủ và (ngân hàng nhà nước|ngân hàng trung ương|nhnnvn|nhnn)( việt nam)?( nhnn)?$"]),
        ("b.interbank_liab", [r"^tiền gửi và vay các (tổ chức tài chính( tctc)?, (các )?)?(tổ chức tín dụng|tctd)( tctd)? khác$"]),
        ("b.cust_dep", [r"^tiền gửi của khách hàng$"]),
        ("b.deriv_liab", [r"^các công cụ tài chính phái sinh và các (khoản nợ|công nợ) tài chính khác$"]),
        ("b.trust_funds", [r"^vốn tài trợ, ủy thác đầu tư"]),
        ("b.papers", [r"^phát hành giấy tờ có giá$"]),
        ("b.other_liab", [r"^các khoản nợ khác$"]),
        ("b.tl", [r"^tổng nợ phải trả$"]),
        # Vốn chủ sở hữu: ưu tiên dòng tổng; ngân hàng không in dòng tổng thì lấy dòng mục La Mã có số
        ("b.te", [r"^tổng vốn chủ sở hữu$", r"^vốn chủ sở hữu$", r"^vốn và các quỹ$"]),
        ("b.mi", [r"^lợi ích (của )?cổ đông (không kiểm soát|thiểu số)$"]),
        ("b.tle", [r"^tổng (cộng )?nợ phải trả và vốn chủ sở hữu$", r"^tổng cộng nguồn vốn$"]),
    ],
    "IS": [
        ("b.ii", [r"^thu nhập lãi và các khoản thu nhập tương tự$"]),
        ("b.ie", [r"^chi phí lãi và các (khoản )?chi phí tương tự$"]),
        ("b.nii", [r"^thu nhập lãi thuần$"]),
        ("b.fi", [r"^thu nhập từ hoạt động dịch vụ$"]),
        ("b.fe", [r"^chi phí (từ )?hoạt động dịch vụ$"]),
        ("b.nfee", [r"thuần từ hoạt động dịch vụ$"]),
        ("b.nfx", [r"thuần từ (hoạt động )?kinh doanh ngoại hối( và vàng)?$"]),
        ("b.ntrading", [r"thuần từ (hoạt động )?mua bán chứng khoán kinh doanh$"]),
        ("b.ninv", [r"thuần từ (hoạt động )?mua bán chứng khoán đầu tư$"]),
        ("b.oi", [r"^thu nhập từ (các )?hoạt động khác$"]),
        ("b.oe", [r"^chi phí (cho )?(các )?hoạt động khác$"]),
        ("b.nother", [r"thuần từ (các )?hoạt động (kinh doanh )?khác$"]),
        ("b.equity_inc", [r"^thu nhập từ góp vốn,? mua cổ phần$"]),
        ("b.toi", [r"^tổng thu nhập (từ )?hoạt động( kinh doanh)?$"]),
        ("b.opex", [r"^(tổng )?chi phí hoạt động$"]),
        ("b.ppop", [r"trước chi phí dự phòng rủi.?ro( tín dụng)?$"]),
        ("b.prov", [r"^chi phí(/hoàn nhập)? dự phòng rủi.?ro( tín dụng)?$"]),
        ("b.pbt", [r"^(tổng )?lợi nhuận trước thuế$"]),
        ("b.cit_cur", [r"thuế (thu nhập doanh nghiệp|tndn) hiện hành$"]),
        ("b.cit_def", [r"thuế (thu nhập doanh nghiệp|tndn) hoãn lại$"]),
        ("b.cit", [r"^(tổng )?chi phí thuế (thu nhập doanh nghiệp|tndn)( trong kỳ)?$"]),
        ("b.npat", [r"^lợi nhuận sau thuế( thu nhập doanh nghiệp| tndn)?$"]),
        ("b.mi", [r"^lợi ích (của )?cổ đông (không kiểm soát|thiểu số)$"]),
        ("b.npat_parent", [r"(phân bổ cho|của) (các )?cổ đông (của )?(ngân hàng|công ty mẹ)$",
                           r"chủ sở hữu (của )?ngân hàng$",
                           r"^lợi nhuận (còn lại|sau thuế|thuần) (của )?(cổ đông )?(của )?ngân hàng$"]),
    ],
    "CF": [
        ("b.cfo", [r"^(lưu chuyển )?tiền thuần .*hoạt động (kinh doanh|kd)$"]),
        ("b.cfi", [r"^(lưu chuyển )?tiền thuần .*hoạt động đầu tư$"]),
        ("b.cff", [r"^(lưu chuyển )?tiền thuần .*hoạt động tài chính$"]),
        ("b.net", [r"^(lưu chuyển )?tiền thuần trong (kỳ|năm)$"]),
        ("b.cash_begin", [r"^tiền và các khoản tương đương tiền .*(đầu kỳ|đầu năm|ngày 0?1 tháng 0?1)"]),
        ("b.fx", [r"ảnh hưởng .*tỷ giá"]),
        ("b.cash_end", [r"^tiền và các khoản tương đương tiền .*(cuối kỳ|cuối năm|ngày 3[01] tháng)"]),
    ],
}

_STT_PREFIX = re.compile(r"^(?:[ivxlc]+|\d+|[a-z])[.)]\s+")


def clean_label(label: str) -> str:
    t = unicodedata.normalize("NFC", label or "").casefold()
    t = re.sub(r"[()“”\"'*]", " ", t)
    t = re.sub(r"\s+", " ", t).replace(" ,", ",").strip(" .:;-–")
    return _STT_PREFIX.sub("", t)


def fold(text: str) -> str:
    """Bỏ dấu thanh và dấu mũ (đ -> d) để so khớp không phụ thuộc kiểu bỏ dấu cũ/mới ("khóan"/"khoán",
    "uỷ"/"ủy") hay lỗi dấu khi đọc ảnh."""
    t = unicodedata.normalize("NFD", text)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.replace("đ", "d").replace("Đ", "D")


def canonicalize(extracted: list[ExtractedStatement]) -> dict[str, list[str]]:
    """Gán mã chuẩn (b.*) cho các dòng chưa có mã. Trả về {báo cáo: [mã chuẩn không tìm thấy]}."""
    missing: dict[str, list[str]] = {}
    for st in extracted:
        for it in st.items:
            # BCTC ngân hàng không có cột mã số; số mô hình ghi vào đó thường là số thuyết minh (ví dụ TCB)
            if it.code and not it.note:
                it.note = it.code
            it.code = None
        items = [(it, fold(clean_label(it.label))) for it in st.items]
        for canonical, patterns in _PATTERNS.get(st.statement, []):
            hit = None
            for pattern in (fold(p) for p in patterns):
                hit = next((it for it, lab in items
                            if it.code is None and re.search(pattern, lab)
                            and any(v not in (None, "", "-") for v in it.values_raw.values())), None)
                if hit:
                    break
            if hit:
                hit.code = canonical
            else:
                missing.setdefault(st.statement, []).append(canonical)
    return missing
