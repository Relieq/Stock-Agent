from pathlib import Path

import pytest

from services.ingestion.titles import parse_title
from services.ingestion.vietstock import parse_dotnet_date

FIXTURE = Path(__file__).parent / "fixtures" / "vietstock_titles_vn30_2025_2026.txt"


def _real_titles() -> list[str]:
    lines = FIXTURE.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line and not line.startswith("#")]


@pytest.mark.parametrize("title", _real_titles())
def test_every_real_title_is_recognized(title):
    assert parse_title(title).is_recognized, title


@pytest.mark.parametrize(
    "title, expected",
    [
        ("BCTC Hợp nhất quý 2 năm 2026 ",
         ("full", "fs_quarter", 2026, "Q2", "consolidated", "none", False)),
        ("BCTC Công ty mẹ Soát xét 6 tháng đầu năm 2026",
         ("full", "fs_semiannual", 2026, "H1", "separate", "reviewed", False)),
        ("BCTC Kiểm toán năm 2025",
         ("full", "fs_annual", 2025, "FY", "standalone", "audited", False)),
        ("BCTC quý 2 năm 2026",
         ("full", "fs_quarter", 2026, "Q2", "standalone", "none", False)),
        ("BCTC Hợp nhất Soát xét quý 1 năm 2026",
         ("full", "fs_quarter", 2026, "Q1", "consolidated", "reviewed", False)),
        ("BCTC Công ty mẹ Soát xét 9 tháng đầu năm 2025",
         ("full", "fs_9m", 2025, "9M", "separate", "reviewed", False)),
        ("KQKD Hợp nhất Soát xét quý 3 năm 2025",
         ("income_statement", "fs_quarter", 2025, "Q3", "consolidated", "reviewed", False)),
        ("LCTT Hợp nhất quý 1 năm 2025 (điều chỉnh)",
         ("cash_flow", "fs_quarter", 2025, "Q1", "consolidated", "none", True)),
        ("Thuyết minh BCTC Hợp nhất Kiểm toán năm 2025 (điều chỉnh)",
         ("notes", "fs_annual", 2025, "FY", "consolidated", "audited", True)),
    ],
)
def test_parse_title(title, expected):
    info = parse_title(title)
    assert (info.content_kind, info.doc_type, info.fiscal_year, info.fiscal_period,
            info.scope, info.audit_status, info.is_amended) == expected


def test_unknown_title_is_not_guessed():
    info = parse_title("Nghị quyết Đại hội đồng cổ đông thường niên")
    assert not info.is_recognized
    assert info.content_kind is None and info.fiscal_period is None


def test_parse_dotnet_date():
    dt = parse_dotnet_date("/Date(1785206047917)/")
    assert dt is not None and dt.isoformat().startswith("2026-07-28T02:34:07")
    assert parse_dotnet_date(None) is None
    assert parse_dotnet_date("không phải ngày") is None
