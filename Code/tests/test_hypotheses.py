"""Giả thuyết do code chọn (services/causes/hypotheses.py): không CSDL, không gọi mô hình."""
from decimal import Decimal as D
from types import SimpleNamespace

from services.causes.decompose import MINORITY, Breakdown, Part
from services.causes.hypotheses import (COMPUTED, UNVERIFIED, Hypothesis, attach_letter, bank_unusual, gross_split,
                                        one_off, scope_change)
from services.metrics.card import Value

B = D(10) ** 9
CODES = {"revenue": "10", "gross_profit": "20", "fin_income": "21", "fin_expense": "22", "interest_expense": "23",
         "jv_profit": "24", "selling_expense": "25", "other_profit": "40", "pbt": "50", "net_fee": "b.nfee",
         "provision": "b.prov"}
LABELS = {"21": "Doanh thu hoạt động tài chính", "22": "Chi phí tài chính", "23": "Trong đó: Chi phí lãi vay",
          "24": "Phần lãi trong công ty liên doanh, liên kết", "40": "Lợi nhuận khác"}


class FakeFacts:
    """Đủ cho các hàm giả thuyết: mã theo mẫu, số hai kỳ (tỷ đồng), tên dòng."""

    def __init__(self, template="TT200", q=None, ytd=None, cf=None):
        self.template = template
        self.q = {CODES.get(k, k): v for k, v in (q or {}).items()}
        self.ytd = {CODES.get(k, k): v for k, v in (ytd or {}).items()}
        self.rows = {("IS", c): SimpleNamespace(label=LABELS.get(c, c), page=1) for c in self.q}
        for code, (label, _) in (cf or {}).items():
            self.rows[("CF", code)] = SimpleNamespace(label=label, page=2)
        self.cf = {code: v for code, (_, v) in (cf or {}).items()}

    def code(self, statement, metric):
        return CODES.get(metric)

    def get(self, statement, code, column, expense=False):
        if statement == "CF":
            v = self.cf.get(code)
        elif column == "q_cur":
            v = self.q.get(code, (None, None))[0]
        elif column == "q_prev_year":
            v = self.q.get(code, (None, None))[1]
        else:
            v = self.ytd.get(code)
        return Value(None if v is None else D(v) * B)

    def metric(self, statement, metric, column):
        return self.get(statement, self.code(statement, metric), column)


def bd(parts, change):
    out = Breakdown("61", D(0), D(-change) * B, parts)
    return out


def test_scope_needs_minority_swing_and_a_strong_sign():
    mi = Part(MINORITY, "Phần lợi nhuận của cổ đông không kiểm soát", D("6.2") * B, D(467) * B, D(461) * B)
    b = bd([mi], -288)
    jv_only = FakeFacts(q={"jv_profit": (797, 131)})
    assert scope_change(jv_only, b) is None             # lãi công ty liên kết đổi một mình chưa đủ
    fpt = FakeFacts(q={"jv_profit": (797, 131), "revenue": (13754, 17205), "selling_expense": (1058, 1917)},
                    ytd={"pbt": 9000},
                    cf={"07": ("Tiền tại công ty con tại thời điểm mất quyền kiểm soát", -713)})
    h = scope_change(fpt, b)
    assert h is not None and h.label == UNVERIFIED
    assert "mất quyền kiểm soát" in h.text and "giảm 461 tỷ (từ 467 tỷ xuống 6,2 tỷ)" in h.text


def test_one_off_both_directions_and_interest_is_not_one_off():
    gvr = FakeFacts(q={"pbt": (4423, 2619), "other_profit": (1998, 459)})
    (h,) = one_off(gvr)
    assert "lợi nhuận khác tăng 1.539 tỷ" in h.text and "85% mức tăng LNTT" in h.text
    fall = FakeFacts(q={"pbt": (1000, 3000), "fin_income": (200, 2000)})
    (h,) = one_off(fall)
    assert "mức giảm LNTT" in h.text
    interest = FakeFacts(q={"pbt": (1389, 1835), "fin_expense": (902, 698), "interest_expense": (850, 687)})
    assert one_off(interest) == []
    assert one_off(FakeFacts("CTCK", q={"pbt": (1389, 1835), "fin_expense": (902, 698)})) == []
    flat = FakeFacts(q={"pbt": (1020, 1000), "other_profit": (300, 100)})
    assert one_off(flat) == []                           # LNTT gần như đi ngang


def test_gross_split_adds_up_and_is_labelled_computed():
    gp = Part("20", "Lợi nhuận gộp", D(4264) * B, D(6519) * B, D(-2255) * B)
    f = FakeFacts(q={"revenue": (13754, 17205), "gross_profit": (4264, 6519)})
    h = gross_split(f, bd([gp], -2255))
    assert h.label == COMPUTED
    by_sales = (D(13754) - D(17205)) * D(6519) / D(17205)
    by_margin = (D(4264) / D(13754) - D(6519) / D(17205)) * D(13754)
    assert abs(by_sales + by_margin - D(-2255)) < D("0.0001")
    assert "giảm từ 37,9% xuống 31,0%" in h.text


def test_bank_line_far_above_history():
    f = FakeFacts("TCTD", q={"net_fee": (4255, 673), "pbt": (3000, 2000)})
    hist = {"net_fee": {(2025, "Q3"): D(673) * B, (2025, "Q4"): D(1300) * B, (2026, "Q1"): D(1400) * B,
                        (2026, "Q2"): D(2000) * B}}
    (h,) = bank_unusual(f, hist, 2026, "Q3")
    assert "gấp 3,2 lần trung bình 4 quý trước (1.343 tỷ)" in h.text
    short = {"net_fee": {(2026, "Q2"): D(1000) * B}}
    assert bank_unusual(f, short, 2026, "Q3") == []      # thiếu lịch sử


def test_letter_mention_by_keywords():
    hs = [Hypothesis("bank_unusual", "", "", "", words="b.nfee"), Hypothesis("one_off", "", "", "", words="other")]
    attach_letter(hs, ["Thu thuần từ hoạt động dịch vụ tăng 3.581,5 tỷ đồng", "Chi phí hoạt động tăng"])
    assert hs[0].company == "công văn có nhắc tới" and "dịch vụ" in hs[0].company_text
    assert hs[1].company == "công văn không nhắc tới"
    attach_letter(hs, None)
    assert {h.company for h in hs} == {"chưa có công văn"}
    # "chi phí" không được tính là nhắc tới phí dịch vụ
    attach_letter(hs[:1], ["Chi phí dự phòng tăng"])
    assert hs[0].company == "công văn không nhắc tới"
