import io
from datetime import datetime, timezone

import openpyxl

from services.api.export import workbook


def test_excel_keeps_printed_numbers_unit_and_source():
    rows = [{"stt": None, "code": c, "label": l, "note": None, "page": 5, "values": {"end_period": v, "begin_year": v}}
            for c, l, v in (("100", "TÀI SẢN NGẮN HẠN", "60"), ("200", "TÀI SẢN DÀI HẠN", "40"),
                            ("280", "TỔNG CỘNG TÀI SẢN", "100"), ("300", "NỢ PHẢI TRẢ", "(70)"),
                            ("400", "VỐN CHỦ SỞ HỮU", "30"), ("440", "TỔNG CỘNG NGUỒN VỐN", "100"))]
    record = {"company_template": "corporate", "chosen": "bctc.pdf",
              "candidates": [{"name": "bctc.pdf", "page_count": 40, "statement_pages": {"BS": [5]}}],
              "raw": {"BS": {"unit_text": "Đơn vị tính: triệu đồng", "rows": rows}},
              "manual_fixes": [{"statement": "BS", "row": 4, "column_kind": "end_period", "label": "VỐN CHỦ SỞ HỮU",
                                "before": "36", "after": "30", "note": "trang 5"}]}
    info = {"ticker": "ABC", "name": "Công ty ABC", "title": "BCTC Hợp nhất quý 3 năm 2026", "period_text": "quý 3/2026",
            "scope_text": "hợp nhất", "source": "HOSE", "source_url": "https://staticfile.hsx.vn/x.pdf",
            "first_at": datetime(2026, 10, 20, 7, 3, tzinfo=timezone.utc), "first_source": "HOSE",
            "processed_at": datetime(2026, 10, 20, 7, 20, tzinfo=timezone.utc), "status_text": "đã kiểm chứng tự động",
            "gate": (4, 4)}
    wb = openpyxl.load_workbook(io.BytesIO(workbook(record, None, info)))
    assert wb.sheetnames == ["Nguồn", "Cân đối kế toán"]
    ws = wb["Cân đối kế toán"]
    assert "đơn vị: triệu đồng" in ws["A1"].value
    assert [c.value for c in ws[6]][:6] == [None, "300", "NỢ PHẢI TRẢ", None, -70, -70]   # số trong ngoặc là số âm
    src = {r[0]: r[1] for r in wb["Nguồn"].iter_rows(values_only=True) if r[0]}
    assert src["Công bố sớm nhất"] == "14:03 20/10/2026 (HOSE)" and "1 ô" in src["Ô đã sửa tay sau khi đối chiếu ảnh"]
