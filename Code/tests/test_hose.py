from datetime import datetime, timezone

from services.ingestion.hose import parse_entry, scope_of


def test_scope_from_hose_file_names():
    # Cách viết đã gặp trên HOSE (VN30, 2025-2026)
    assert scope_of("20261019 - VPB - BCTC hop nhat quy 3 nam 2026.pdf") == "consolidated"
    assert scope_of("20260730 - BID - CBTT BCTC HN giua nien do Q2.pdf") == "consolidated"
    assert scope_of("20260130 - VHM - BCTC HN Q4 nam 2025+Giai trinh (Viet+Anh).pdf") == "consolidated"
    assert scope_of("20260730 - BID - CBTT BCTC RL giua nien do Q2.pdf") == "separate"
    assert scope_of("20260429 - VJC - BCTC Cong ty me 1.2026 VN seal.pdf") == "separate"
    assert scope_of("20260202 - GAS - Bao cao tai chinh Quy 4. 2025 CTM.pdf") == "separate"
    assert scope_of("20261019 - VPB - BCTC rieng le quy 3 nam 2026.pdf") == "separate"
    assert scope_of("20260715 - TCX - BCTC Q2.2026.pdf") is None          # BCTC duy nhất


def test_parse_hose_media_file():
    x = {"fileName": "20261019 - VPB - BCTC hop nhat quy 3 nam 2026.pdf", "fileType": ".pdf",
         "filePath": "~/Uploads/UploadDocuments/2505480/20261019 - VPB - BCTC hop nhat quy 3 nam 2026.pdf",
         "relatedType": 5, "time": "03.2026", "type": "Quý", "createdDate": 1792461902}
    st = parse_entry("VPB", x)
    assert (st.doc_type, st.fiscal_period, st.fiscal_year, st.scope, st.is_amended) == ("fs_quarter", "Q3", 2026,
                                                                                         "consolidated", False)
    assert st.url == ("https://staticfile.hsx.vn/Uploads/UploadDocuments/2505480/"
                      "20261019%20-%20VPB%20-%20BCTC%20hop%20nhat%20quy%203%20nam%202026.pdf")
    assert st.posted_at == datetime.fromtimestamp(1792461902, tz=timezone.utc)
    assert st.source_doc_id.startswith("2505480/") and len(st.source_doc_id) <= 40
    assert parse_entry("VPB", x | {"type": "Bán niên", "time": "2026"}).fiscal_period == "H1"
    assert parse_entry("VPB", x | {"relatedType": 1}) is None              # tin thường, không phải BCTC
    assert parse_entry("VPB", x | {"type": "Tháng", "time": "09.2026"}) is None
    assert parse_entry("VPB", x | {"fileName": "BCTC hop nhat Q3 2026 (dieu chinh).pdf"}).is_amended


def test_vietstock_scan_stops_after_consecutive_failures():
    from services.ingestion import registry

    class Down:
        calls = 0

        def list_financial_statements(self, ticker, year=None):
            Down.calls += 1
            raise TimeoutError("Read timed out")

    stats = registry.discover(None, Down(), ["A", "B", "C", "D", "E"], 2026)
    assert Down.calls == registry.MAX_FAILS_IN_ROW and stats["errors"] == registry.MAX_FAILS_IN_ROW + 1
