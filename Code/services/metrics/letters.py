"""Nguyên nhân biến động lợi nhuận công ty nêu trong công văn giải trình, kèm kết quả đối chiếu với BCTC đã kiểm chứng,
để hiện trên thẻ KQKD.

Công văn được đọc một lần khi bộ canh tải về (khoảng 0,002 USD mỗi công văn) và lưu ở Data/raw/explanations/<id>.json;
trang thẻ chỉ đọc bản đã lưu, không gọi mô hình. Phép đối chiếu chạy lại mỗi lần hiện thẻ nên luôn theo số BCTC mới nhất
(kể cả sau khi sửa tay).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import psycopg

from services.analyst.explanations import check_section, facts_for, load_letter
from services.ingestion.registry import raw_data_dir

# Nhãn trên thẻ cho từng kết quả đối chiếu (lớp màu, lời)
VERDICTS = {"khớp": ("ok", "khớp BCTC"), "khớp chiều": ("ok", "đúng chiều tăng/giảm trên BCTC"),
            "không kiểm được": ("muted", "theo công ty, chưa kiểm được bằng số"),
            "lệch": ("bad", "lệch với BCTC"), "ngược chiều": ("bad", "ngược chiều với BCTC")}
HEADLINE = ("lợi nhuận", "doanh thu", "% thay đổi")
MAX_PER_PASS = 20           # bộ canh đọc tối đa ngần này công văn mỗi lượt


@dataclass
class Reason:
    text: str
    css: str
    verdict: str
    detail: str = ""        # số công ty nêu và số trên BCTC, hoặc vì sao chưa kiểm được


@dataclass
class LetterView:
    read: bool
    period_kind: str | None = None          # quarter / ytd / half_year / year: phần công văn đang hiện
    headline: list[Reason] = field(default_factory=list)
    reasons: list[Reason] = field(default_factory=list)
    only_separate: bool = False             # công văn chỉ nói về BCTC riêng công ty mẹ, thẻ là hợp nhất


def _cached(doc_id: int) -> dict | None:
    path = raw_data_dir() / "explanations" / f"{doc_id}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _section(sections: list[dict], scope: str) -> dict | None:
    """Phần dùng cho thẻ quý: cùng phạm vi BCTC (hợp nhất hoặc riêng duy nhất), ưu tiên phần nói về riêng quý."""
    same = [s for s in sections if s["scope"] != "separate" or scope == "separate"]
    for kind in ("quarter", "ytd", "half_year", "year"):
        for s in same:
            if s["period_kind"] == kind:
                return s
    return None


def _reason(c) -> Reason:
    css, label = VERDICTS.get(c.verdict, ("muted", c.verdict))
    if c.verdict in ("khớp", "lệch"):
        detail = f"công ty nêu {c.stated}, BCTC {c.bctc}" if c.stated and c.bctc else ""
    elif c.verdict in ("khớp chiều", "ngược chiều"):
        detail = f"BCTC: {c.bctc}" if c.bctc else ""
    else:
        detail = c.note
    if c.note and c.verdict == "khớp" and "khớp" in c.note:
        detail = f"{detail}; {c.note}" if detail else c.note
    return Reason(c.what, css, label, detail)


def letter_view(conn: psycopg.Connection, letter_id: int, ticker: str, year: int, period: str,
                scope: str) -> LetterView:
    """Nguyên nhân trong công văn `letter_id` cho thẻ quý (`period`) của `ticker`; read=False nếu chưa đọc công văn."""
    data = _cached(letter_id)
    if data is None:
        return LetterView(read=False)
    sections = data.get("sections", [])
    sec = _section(sections, scope)
    if sec is None:
        return LetterView(read=True, only_separate=any(s["scope"] == "separate" for s in sections))
    res = check_section(sec, facts_for(conn, ticker, year, period, sec["scope"], sec["period_kind"]))
    return build_view(sec, res)


def build_view(sec: dict, res) -> LetterView:
    view = LetterView(read=True, period_kind=sec["period_kind"])
    # Phép đối chiếu nguyên nhân nằm cuối danh sách, theo thứ tự trong công văn; lời nguyên nhân lấy bản đầy đủ (phép
    # đối chiếu chỉ giữ 120 ký tự đầu)
    texts = [r["text"] for r in sec.get("reasons", [])]
    first_reason = len(res.checks) - len(texts) if texts and res.checks[-1].what != "cả phần" else len(res.checks)
    for i, c in enumerate(res.checks):
        if c.what == "cả phần":
            view.headline.append(Reason("Chưa đối chiếu được", "muted", "", c.note))
        elif i >= first_reason:
            r = _reason(c)
            r.text = texts[i - first_reason]
            view.reasons.append(r)
        else:
            view.headline.append(_reason(c))
    return view


def read_pending(conn: psycopg.Connection, client, limit: int = MAX_PER_PASS) -> list[str]:
    """Đọc các công văn giải trình đã tải về mà chưa đọc (mã đang theo dõi, từ năm 2025). Trả về dòng báo quản trị."""
    rows = conn.execute(
        """SELECT d.id, d.ticker, d.fiscal_period, d.fiscal_year FROM documents d
           WHERE d.doc_type = 'explanation' AND d.duplicate_of IS NULL AND d.owner_user_id IS NULL
             AND d.fiscal_year >= 2025 AND d.ticker IN (SELECT ticker FROM companies WHERE tracked)
             AND EXISTS (SELECT 1 FROM document_files f WHERE f.document_id = d.id)
           ORDER BY d.discovered_at DESC""").fetchall()
    todo = [r for r in rows if _cached(r[0]) is None][:limit]
    if not todo or client is None:
        return []
    before, read = client.usage.usd, []
    for doc_id, ticker, period, year in todo:
        try:
            load_letter(conn, client, doc_id)
            read.append(f"{ticker} {period}/{year}")
        except Exception as e:      # noqa: BLE001 - một công văn lỗi không làm hỏng lượt canh
            read.append(f"{ticker} {period}/{year} LỖI {e}")
    return [f"Đọc {len(read)} công văn giải trình ({client.usage.usd - before:.3f} USD): {', '.join(read)}"]
