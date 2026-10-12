from services.ondemand import parse_company_title


def test_company_name_and_template_from_vietstock_title():
    html = "<html><title>HUT: CTCP Tasco - Tasco - CTCP - Tải tài liệu | VietstockFinance</title>"
    assert parse_company_title("HUT", html) == ("CTCP Tasco", "corporate")
    html = "<title>\n  VAB: Ngân hàng TMCP Việt Á - VietABank - Tải tài liệu | VietstockFinance</title>"
    assert parse_company_title("VAB", html) == ("Ngân hàng TMCP Việt Á", "bank")
    assert parse_company_title("XYZ", "<title>Không tìm thấy</title>") is None


def test_upload_must_match_declared_company_and_period():
    from services.ondemand import check_upload, names_match
    assert names_match("CÔNG TY CỔ PHẦN TASCO", "CTCP Tasco")
    assert not names_match("Công ty Cổ phần Đầu tư Hạ tầng Kỹ thuật", "CTCP Tasco")
    ok = {"is_financial_statement": True, "company_name": "Công ty Cổ phần Tasco", "ticker": None,
          "fiscal_year": 2026, "period": "Q2", "scope": "consolidated"}
    assert check_upload(ok, "HUT", "CTCP Tasco", 2026, "Q2") is None
    assert "không khớp HUT" in check_upload(ok | {"company_name": "Công ty Cổ phần FPT"}, "HUT", "CTCP Tasco", 2026, "Q2")
    assert "Q1/2026" in check_upload(ok | {"period": "Q1"}, "HUT", "CTCP Tasco", 2026, "Q2")
    assert check_upload(ok | {"ticker": "HUD"}, "HUT", "CTCP Tasco", 2026, "Q2") == "File in mã HUD, không phải HUT"
    assert check_upload(ok | {"is_financial_statement": False}, "HUT", "CTCP Tasco", 2026, "Q2") == "File không phải báo cáo tài chính"
