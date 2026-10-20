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
    ok = {"document_kind": "financial_statement", "is_financial_statement": True, "company_name": "Công ty Cổ phần Tasco", "ticker": None,
          "fiscal_year": 2026, "period": "Q2", "scope": "consolidated"}
    assert check_upload(ok, "HUT", "CTCP Tasco", 2026, "Q2") is None
    assert "không khớp HUT" in check_upload(ok | {"company_name": "Công ty Cổ phần FPT"}, "HUT", "CTCP Tasco", 2026, "Q2")
    assert "Q1/2026" in check_upload(ok | {"period": "Q1"}, "HUT", "CTCP Tasco", 2026, "Q2")
    assert check_upload(ok | {"ticker": "HUD"}, "HUT", "CTCP Tasco", 2026, "Q2") == "File in mã HUD, không phải HUT"
    assert check_upload(ok | {"is_financial_statement": False}, "HUT", "CTCP Tasco", 2026, "Q2") == "File không phải báo cáo tài chính"


def test_explanation_letter_upload_is_rejected_with_a_clear_reason():
    # VPB quý 3/2026: người dùng tải lên công văn giải trình lợi nhuận, không phải BCTC
    from services.ondemand import check_upload
    letter = {"document_kind": "explanation_letter", "is_financial_statement": False, "company_name": "Ngân hàng TMCP Việt Nam Thịnh Vượng",
              "ticker": "VPB", "fiscal_year": 2026, "period": "Q3", "scope": None}
    assert "công văn giải trình" in check_upload(letter, "VPB", "Ngân hàng TMCP Việt Nam Thịnh Vượng", 2026, "Q3")


def test_no_schema_has_nullable_enums():
    # API của Anthropic từ chối enum đi kèm kiểu ["string", "null"] (lỗi 400 làm hỏng mọi file tải lên, 20/10/2026)
    from services.extraction import prompts

    def walk(node):
        if isinstance(node, dict):
            if "enum" in node:
                assert not isinstance(node.get("type"), list) and None not in node["enum"], node
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    schemas = [v for k, v in vars(prompts).items() if k.endswith("_SCHEMA")]
    schemas += [prompts.extract_schema(st) for st in ("BS", "IS", "CF")]
    assert len(schemas) >= 6
    for schema in schemas:
        walk(schema)
