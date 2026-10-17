from services.extraction.repair import agrees, digits_changed, format_like, localize
from services.extraction.validate import ExtractedItem, ExtractedStatement, normalize, validate


def _bs(rows):
    return ExtractedStatement("BS", "VND", [ExtractedItem(code, label, {"end_period": v}) for code, label, v in rows])


# Tài sản cố định theo TT200, số như BCTC FPT quý 4/2025 (đơn vị đồng, rút gọn)
FIXED_ASSETS = [
    ("220", "Tài sản cố định", "17.330.033"),
    ("221", "Tài sản cố định hữu hình", "15.385.816"),
    ("222", "Nguyên giá", "29.148.692"),
    ("223", "Hao mòn", "(13.762.876)"),
    ("224", "Tài sản cố định thuê tài chính", "1.271"),       # đọc sai: in 1.277
    ("225", "Nguyên giá", "5.871"),
    ("226", "Hao mòn", "(4.594)"),
    ("227", "Tài sản cố định vô hình", "1.942.940"),
    ("228", "Nguyên giá", "3.868.884"),
    ("229", "Hao mòn", "(1.925.944)"),
]


def _localize(rows):
    extracted = [_bs(rows)]
    statements, sep = normalize(extracted)
    return localize(extracted, statements, sep, "TT200")


def test_cell_explaining_two_failed_sums_is_proposed_with_high_confidence():
    loc = _localize(FIXED_ASSETS)
    assert [(p.code, p.after, p.confidence) for p in loc.proposals] == [("224", "1.277", "cao")]
    assert sorted(loc.proposals[0].fixes) == ["BS_220@end_period", "BS_224@end_period"]
    assert not loc.ambiguous and not loc.unresolved


def test_single_failed_sum_gives_a_group_to_reread():
    rows = [r if r[0] != "224" else ("224", "", "1.277") for r in FIXED_ASSETS]
    rows = [r if r[0] != "228" else ("228", "Nguyên giá", "3.868.384") for r in rows]   # 8 -> 3
    loc = _localize(rows)
    assert not loc.proposals
    assert len(loc.ambiguous) == 1
    group = {p.code: p.after for p in loc.ambiguous[0]}
    assert group["228"] == "3.868.884"          # phương án đúng nằm trong nhóm để đọc lại
    assert set(group) <= {"227", "228", "229"}


def test_two_cells_off_by_the_same_amount_are_fixed_together():
    # Thu nhập khác và lãi khác cùng lệch 50 nên 40 = 31 - 32 vẫn khớp; chỉ 50 = 30 + 40 lệch (VHM quý 4/2025)
    is_rows = [("01", "Doanh thu", "1.000"), ("02", "Giảm trừ", "0"), ("10", "Doanh thu thuần", "1.000"),
               ("11", "Giá vốn", "600"), ("20", "Lãi gộp", "400"), ("21", "DT tài chính", "0"),
               ("22", "CP tài chính", "0"), ("25", "CP bán hàng", "0"), ("26", "CP quản lý", "0"),
               ("30", "LN thuần", "400"), ("31", "Thu nhập khác", "1.680"), ("32", "Chi phí khác", "906"),
               ("40", "Lãi khác", "774"), ("50", "LNTT", "1.124"), ("51", "Thuế", "100"), ("52", "Hoãn lại", "0"),
               ("60", "LNST", "1.024")]
    extracted = [ExtractedStatement("IS", "VND", [ExtractedItem(c, l, {"ytd_cur": v}) for c, l, v in is_rows])]
    statements, sep = normalize(extracted)
    loc = localize(extracted, statements, sep, "TT200")
    found = {(p.code, p.after) for p in loc.proposals} | {(q.code, q.after) for g in loc.ambiguous for p in g
                                                          for q in (p, p.partner) if q}
    assert {("31", "1.630"), ("40", "724")} <= found


def test_no_proposal_when_everything_adds_up():
    rows = [r if r[0] != "224" else ("224", "", "1.277") for r in FIXED_ASSETS]
    statements, _ = normalize([_bs(rows)])
    assert all(c.passed for c in validate(statements, "TT200") if c.gate)
    assert not _localize(rows).proposals


def test_helpers():
    assert digits_changed("1.271.212.606", "1.277.212.606") == 1
    assert digits_changed("4.714.930", "471.930") == 1           # thừa một chữ số
    assert format_like("(1.234)", -5678, ".") == "(5.678)"
    assert format_like("-1,234", -5678, ",") == "-5,678"
    p = {"before": "(8.334.366)", "after": "(8.374.366)"}
    assert agrees(p, "(8,374,366)", ".", 1)                      # lần đọc lại viết dấu phẩy
    assert agrees(p, "8.374.366", ".", 1)                        # lần đọc lại bỏ mất dấu ngoặc
    assert not agrees(p, "(8.334.366)", ".", 1)


def test_confusion_model_ranks_common_misreads_first():
    # Nhầm 6->8 hay gặp (10 lần), nhầm 9->2 chưa gặp: ô đọc "1.238" (đúng 1.236) đứng trước ô đọc "5.432" (đúng 5.439)
    from decimal import Decimal
    from services.extraction.confusion import count_substitutions, log_likelihood
    from services.extraction.repair import Proposal, rank_group
    table = count_substitutions([("1.238", "1.236")] * 10 + [("17", "11")] * 9)
    assert table == {"6": {"8": 10}, "1": {"7": 9}}
    assert log_likelihood("1.238", "1.236", table) > log_likelihood("5.432", "5.439", table)
    assert log_likelihood("4.714.930", "471.930", table) > log_likelihood("4.714.930", "471.000", table)  # thừa 1 chữ số
    a = Proposal("BS", "131", "end_period", 3, "a", "5.432", "5.439", Decimal(5439), ["BS_130@end_period"], 1)
    b = Proposal("BS", "132", "end_period", 4, "b", "1.238", "1.236", Decimal(1236), ["BS_130@end_period"], 1)
    ranked = rank_group([a, b], table)
    assert ranked[0] is b and b.prob > 0.8 and abs(a.prob + b.prob - 1) < 1e-9


def test_dominant_candidate_needs_clear_majority():
    import types
    from services.extraction.pipeline import _dominant
    p = lambda prob: types.SimpleNamespace(prob=prob)
    strong, weak = p(0.95), p(0.05)
    assert _dominant([strong, weak]) is strong
    assert _dominant([p(0.6), p(0.4)]) is None
    assert _dominant([]) is None
