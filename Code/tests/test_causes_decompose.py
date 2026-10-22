"""Tách mức thay đổi LNST theo dòng KQKD bằng ràng buộc kế toán (không CSDL, không gọi mô hình)."""
from decimal import Decimal as D

from services.causes.decompose import MINORITY, decompose, top_parts


def _v(**kw):
    # mã -> (kỳ này, cùng kỳ) ; mã có dấu chấm viết bằng gạch dưới
    return {k.replace("_", ".").lstrip("c"): {"q_cur": D(a), "q_prev_year": D(b)} for k, (a, b) in kw.items()}


def test_corporate_parts_sum_to_parent_profit_change():
    v = _v(c10=(1000, 800), c11=(600, 500), c20=(400, 300), c21=(50, 20), c22=(30, 30), c25=(100, 80), c26=(60, 50),
           c30=(260, 160), c31=(5, 0), c32=(5, 0), c40=(0, 0), c50=(260, 160), c51=(50, 30), c60=(210, 130),
           c61=(200, 125), c62=(10, 5))
    bd = decompose("TT200", v, {"20": "Lợi nhuận gộp"}, flip=False)
    assert bd.target == "61" and bd.change == 75 and bd.ok and bd.residual == 0
    eff = {p.code: p.effect for p in bd.parts}
    assert eff["20"] == 100 and eff["21"] == 30 and eff["25"] == -20 and eff["51"] == -20 and eff[MINORITY] == -5
    assert [p.code for p in top_parts(bd)] == ["20"]


def test_expenses_printed_negative_are_added():
    v = _v(c20=(400, 300), c25=(-100, -80), c30=(300, 220), c50=(300, 220), c51=(-60, -44), c60=(240, 176))
    bd = decompose("TT200", v, {}, flip=True)
    assert bd.ok and bd.target == "60"
    eff = {p.code: p.effect for p in bd.parts}
    assert eff["25"] == -20 and eff["51"] == -16 and eff["20"] == 100
    kind = {p.code: p.expense for p in bd.parts}
    assert kind["25"] and kind["51"] and not kind["20"]           # in số âm vẫn nhận ra là khoản trừ


def test_bank_breakdown_and_mismatch_is_reported():
    v = _v(b_nii=(100, 80), b_nfee=(20, 10), b_toi=(120, 90), b_opex=(40, 30), b_ppop=(80, 60), b_prov=(10, 20),
           b_pbt=(70, 40), b_cit=(14, 8), b_npat=(56, 32))
    bd = decompose("TCTD", v, {}, flip=False)
    assert bd.ok and {p.code: p.effect for p in bd.parts}["b.prov"] == 10
    v["b.npat"]["q_cur"] = D(60)               # LNST không khớp các dòng: không giải thích
    assert not decompose("TCTD", v, {}, flip=False).ok


def test_unsupported_template_or_missing_columns():
    assert decompose("BH", {}, {}, flip=False) is None
    assert decompose("TT200", {"60": {"q_cur": D(1)}}, {}, flip=False) is None
