import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("methods_eval", Path(__file__).parent.parent / "eval" / "methods.py")
methods = importlib.util.module_from_spec(spec)
spec.loader.exec_module(methods)


def _w(x0, y, text, width=None):
    """Hộp chữ giả: chữ cao 8 điểm, rộng 5 điểm mỗi ký tự."""
    x1 = x0 + (width if width is not None else 5 * len(text))
    return (x0, y, x1, y + 8, text)


def _num(right, y, text):
    """Số tiền canh phải tại hoành độ `right`."""
    return _w(right - 5 * len(text), y, text)


def test_map_kinds_by_order():
    assert methods.map_kinds("IS", 4) == ["q_cur", "q_prev_year", "ytd_cur", "ytd_prev_year"]
    assert methods.map_kinds("IS", 2) == ["q_cur", "q_prev_year"]          # KQKD quý 1: hai cột
    assert methods.map_kinds("BS", 3) == ["end_period", "begin_year"]      # thừa cột thì chỉ giữ số loại của báo cáo
    assert methods.map_kinds("CF", 1) == ["ytd_cur"]
    assert methods.map_kinds("CF", 0) == []


def _page_bs():
    words = []
    rows = [("1. Tiền", "111", "1.000.000", "900.000"),
            ("2. Các khoản tương đương tiền", "112", "2.000.000", "(300.000)"),
            ("Tổng tiền", "110", "3.000.000", "600.000"),
            ("Phải thu", "130", "4.000", "-")]
    for k, (label, code, a, b) in enumerate(rows):
        y = 100 + 20 * k
        words += [_w(40, y, t) for t in label.split()[:1]]
        words += [_w(70 + 30 * i, y, t) for i, t in enumerate(label.split()[1:])]
        words += [_w(250, y, code), _num(450, y, a), _num(550, y, b)]
    return words


def test_rows_from_words_columns_code_and_stt():
    rows = methods.rows_from_words(_page_bs(), 3, "BS")
    assert [r["code"] for r in rows] == ["111", "112", "110", "130"]
    assert rows[0]["stt"] == "1" and rows[0]["label"] == "Tiền"
    assert rows[1]["values"] == {"end_period": "2.000.000", "begin_year": "(300.000)"}
    assert rows[3]["values"] == {"end_period": "4.000", "begin_year": "-"}
    assert all(r["page"] == 3 for r in rows)


def test_rows_from_words_label_and_numbers_on_different_lines():
    # Tên ở hàng trên, mã số và số ở hàng dưới (bảng kẻ ô, chữ canh trên còn số canh giữa)
    words = [_w(40, 100, "Doanh"), _w(80, 100, "thu"),
             _w(250, 112, "01"), _num(450, 124, "5.000.000"), _num(550, 124, "4.000.000"),
             _w(40, 150, "Giá"), _w(70, 150, "vốn"), _w(250, 150, "11"),
             _num(450, 150, "(3.000.000)"), _num(550, 150, "(2.000.000)"),
             _w(40, 170, "Lãi"), _w(70, 170, "gộp"), _w(250, 170, "20"),
             _num(450, 170, "2.000.000"), _num(550, 170, "2.000.000"),
             _w(40, 190, "Chi"), _w(70, 190, "phí"), _w(250, 190, "25"),
             _num(450, 190, "(100.000)"), _num(550, 190, "(90.000)")]
    rows = methods.rows_from_words(words, 6, "IS")
    assert [(r["code"], r["label"]) for r in rows] == [("01", "Doanh thu"), ("11", "Giá vốn"), ("20", "Lãi gộp"),
                                                         ("25", "Chi phí")]
    assert rows[0]["values"]["q_cur"] == "5.000.000" and rows[0]["values"]["q_prev_year"] == "4.000.000"
    assert rows[0]["values"]["ytd_cur"] is None


def test_rows_from_words_wrapped_label_lowercase_continuation():
    words = [_w(40, 100, "3."), _w(60, 100, "Lợi"), _w(90, 100, "nhuận"), _w(130, 100, "trước"),
             _w(60, 112, "thay"), _w(90, 112, "đổi"), _w(120, 112, "vốn"), _w(250, 112, "08"),
             _num(450, 112, "1.000.000"), _num(550, 112, "2.000.000"),
             _w(40, 140, "Tăng"), _w(70, 140, "phải"), _w(100, 140, "thu"), _w(250, 140, "09"),
             _num(450, 140, "3.000"), _num(550, 140, "4.000"),
             _w(40, 160, "Tăng"), _w(70, 160, "tồn"), _w(250, 160, "10"),
             _num(450, 160, "5.000"), _num(550, 160, "6.000"),
             _w(40, 180, "Tăng"), _w(70, 180, "trả"), _w(250, 180, "11"),
             _num(450, 180, "7.000"), _num(550, 180, "8.000")]
    rows = methods.rows_from_words(words, 8, "CF")
    assert rows[0]["label"] == "Lợi nhuận trước thay đổi vốn" and rows[0]["stt"] == "3" and rows[0]["code"] == "08"
    assert rows[0]["values"] == {"ytd_cur": "1.000.000", "ytd_prev_year": "2.000.000"}
    assert len(rows) == 4


def test_clean_words_and_clean_value_remove_table_rules():
    words = methods.clean_words([(0, 0, 100, 8, "3.624.565|"), (110, 0, 150, 8, "|V.04|"), (160, 0, 170, 8, "|")])
    assert [w[4] for w in words] == ["3.624.565", "V.04"]
    assert words[0][2] < 100
    assert methods.clean_value("— 6.267.821.574") == "6.267.821.574"
    assert methods.clean_value("[1.234.567|") == "1.234.567"
    assert methods.clean_value("—") == "—"


def test_split_label_note_and_stt():
    assert methods.split_label(["II.", "Tiền", "gửi", "V.1"]) == ("II", "Tiền gửi", "V.1")
    assert methods.split_label(["V20"]) == (None, "", "V20")
    assert methods.split_label(["110"]) == (None, "110", None)         # một cụm 3 chữ số là mã số, không phải thuyết minh


def test_tesseract_words_scales_to_points():
    tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
           "4\t1\t1\t1\t1\t0\t10\t20\t300\t30\t-1\t\n"
           "5\t1\t1\t1\t1\t1\t10\t20\t100\t30\t96.5\tTiền\n"
           "5\t1\t1\t1\t1\t2\t200\t20\t110\t30\t91\t1.234.567\n"
           "5\t1\t1\t1\t1\t3\t400\t20\t10\t30\t95\t \n")
    words = methods.tesseract_words(tsv, 0.5)
    assert [w[4] for w in words] == ["Tiền", "1.234.567"]
    assert words[1][:4] == (100.0, 10.0, 155.0, 25.0) and words[1][5] == 91.0


def test_rows_from_grid_numeric_and_code_columns():
    grid = [["CHỈ TIÊU", "Mã số", "TM", "Quý này", "Quý trước"],
            ["1. Doanh thu bán hàng", "01", "V.20", "2.139.637.203.726 |", "1.741.244.012.008"],
            ["2. Các khoản giảm trừ", "02", "", "-", "-"],
            ["3. Doanh thu thuần", "10", "", "2.139.637.203.726", "1.741.244.012.008"],
            ["4. Giá vốn hàng bán", "11", "V.22", "(1.844.123.962.479)", "— 1.524.079.388.509"],
            ["5. Lợi nhuận gộp về bán hàng", "20", "", "295.513.241.247", "217.164.623.499"],
            ["và cung cấp dịch vụ", "", "", "", ""]]
    rows = methods.rows_from_grid(grid, 6, "IS")
    by_code = {r["code"]: r for r in rows}
    assert by_code["01"]["values"]["q_cur"] == "2.139.637.203.726" and by_code["01"]["note"] == "V.20"
    assert by_code["11"]["values"]["q_prev_year"] == "1.524.079.388.509"
    assert by_code["20"]["label"] == "Lợi nhuận gộp về bán hàng và cung cấp dịch vụ"
    assert by_code["02"]["values"]["q_cur"] == "-"
    assert methods.rows_from_grid([["a", "b"]], 1, "BS") == []


def test_layout_text_keeps_columns():
    text = methods.layout_text([_w(0, 0, "Tiền"), _num(400, 0, "1.000"), _w(0, 20, "Phải"), _num(400, 20, "20")],
                               page_width=400, chars=80)
    lines = text.splitlines()
    assert len(lines) == 2 and lines[0].startswith("Tiền") and lines[0].endswith("1.000")
    assert lines[0].index("1.000") > 60


def test_revert_first_pass_undoes_logged_fixes():
    record = {"raw": {"BS": {"rows": [{"code": "110", "page": 3, "values": {"end_period": "13.105"}},
                                      {"code": "111", "page": 3, "values": {"end_period": "5"}},
                                      {"code": "300", "page": 6, "values": {"end_period": "9"}}]},
                      "IS": {"rows": [{"code": "01", "page": 7, "values": {"q_cur": "1"}}]}},
              "repairs": [{"statement": "BS", "row": 0, "column_kind": "end_period", "before": "15.105",
                           "after": "13.105", "accepted": True},
                          {"statement": "BS", "row": 1, "column_kind": "end_period", "before": "7", "after": "5",
                           "accepted": False}],
              "rereads": [{"statement": "BS", "code": "111", "column_kind": "end_period", "before": "8", "after": "5",
                           "kept": True}],
              "extensions": [{"statement": "BS", "page": 6, "kept": True}],
              "reextracts": [{"statement": "IS", "kept": True}]}
    first, lost = methods.revert_first_pass(record)
    rows = first["raw"]["BS"]["rows"]
    assert [r["values"]["end_period"] for r in rows] == ["15.105", "8"]       # trang chép thêm bị bỏ
    assert lost == ["IS"]
    assert record["raw"]["BS"]["rows"][0]["values"]["end_period"] == "13.105"   # bản gốc không đổi
