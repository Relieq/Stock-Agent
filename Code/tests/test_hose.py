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


def test_explanation_letters_on_hose_get_their_period_from_the_file_name():
    from services.ingestion.hose import parse_letter

    def letter(name, posted):
        x = {"fileName": name, "fileType": ".pdf", "filePath": f"~/Uploads/UploadDocuments/1/{name}", "relatedType": 1,
             "time": "", "type": "", "createdDate": int(datetime(*posted, 9, tzinfo=timezone.utc).timestamp())}
        st = parse_letter("X", x)
        return st and (st.fiscal_period, st.fiscal_year, st.scope)
    # Tên tệp thật trên HOSE (VPB, MSN, SAB, STB, MWG, BSR 2025-2026)
    assert letter("20261019 - VPB - Giai trinh bien dong loi nhuan sau thue quy 3 2026 va 9 thang 2026.pdf",
                  (2026, 10, 19)) == ("Q3", 2026, None)
    assert letter("20260811 - VPB - Giai trinh bien dong LNST tren BCTC ban nien soat xet.pdf",
                  (2026, 8, 11)) == ("H1", 2026, None)
    assert letter("20260717 - VPB - Giai trinh bien dong loi nhuan sau thue Q2.2026 va Q2.2025.pdf",
                  (2026, 7, 17)) == ("Q2", 2026, None)
    assert letter("20260313 - MSN - Giai trinh bien dong loi nhuan cho BCTC kiem toan 2025 - signed.pdf",
                  (2026, 3, 13)) == ("FY", 2025, None)
    assert letter("20260128 - MSN - CBTT link BCTC Q4.2025 va Giai trinh bien dong loi nhuan - signed.pdf",
                  (2026, 1, 28)) == ("Q4", 2025, None)
    assert letter("20260129 - SAB - GIAI TRINH BCTC HOP NHAT QUY 4 2025.pdf", (2026, 1, 29)) == ("Q4", 2025, "consolidated")
    assert letter("20250829 - SAB - GIAI TRINH BCTC RIENG KIEM TOAN BAN NIEN 2025.pdf",
                  (2025, 8, 29)) == ("H1", 2025, "separate")
    assert letter("20260730 - MWG - CV giai trinh BCTC Q2-2026.pdf", (2026, 7, 31)) == ("Q2", 2026, None)
    assert letter("20260130 - BSR - Giai trinh loi nhuan sau thue Quy 4 nam 2025.pdf", (2026, 1, 30)) == ("Q4", 2025, None)
    assert letter("20260326 - BSR - Giai trinh mot so noi dung lien quan BCTC nam 2025 da kiem toan.pdf",
                  (2026, 3, 26)) == ("FY", 2025, None)
    assert letter("20260827 - BSR  - Giai trinh lien quan BCTC ban nien sau soat xet.pdf", (2026, 8, 28)) == ("H1", 2026, None)
    assert letter("20261013 - NTC - TB ngay DKCC thuc hien chi tra co tuc.pdf", (2026, 10, 13)) is None


def test_correction_notice_is_not_an_explanation_letter():
    from services.ingestion.hose import parse_letter
    name = "20260904 - VHM - Dinh Chinh Bao cao tai chinh hop nhat soat xet Q2 nam 2026 va giai trinh.pdf"
    x = {"fileName": name, "fileType": ".pdf", "filePath": f"~/Uploads/UploadDocuments/1/{name}", "relatedType": 1,
         "time": "", "type": "", "createdDate": 1788480000}
    assert parse_letter("VHM", x) is None
