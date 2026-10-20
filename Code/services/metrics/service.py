"""Lắp thẻ KQKD cho một BCTC từ CSDL và các bản ghi trích xuất đã lưu (không gọi mô hình)."""

from __future__ import annotations

from decimal import Decimal

import psycopg

from services.extraction.evidence import document_evidence
from services.extraction.pipeline import _load_record
from services.metrics.card import Card, Facts, build_card

PUBLISHABLE = ("verified", "approved")   # tự đạt kiểm chứng, hoặc người duyệt đã đối chiếu ảnh gốc


def _record(conn, document_id: int) -> dict | None:
    try:
        return _load_record(conn, document_id)
    except RuntimeError:
        return None


def npat_history(conn: psycopg.Connection, ticker: str, scope: str) -> dict[tuple[int, str], Decimal]:
    """LNST của cổ đông công ty mẹ theo quý, lấy từ các BCTC quý đã kiểm chứng hoặc đã duyệt tay: cột quý này cho chính quý đó, cột cùng kỳ cho
    quý năm trước (khi chưa có BCTC của quý năm trước)."""
    rows = conn.execute(
        """SELECT id, fiscal_year, fiscal_period FROM documents
           WHERE ticker = %s AND scope = %s AND doc_type = 'fs_quarter' AND status IN ('verified', 'approved')
             AND content_kind = 'full' AND NOT is_amended AND owner_user_id IS NULL
           ORDER BY fiscal_year, fiscal_period, source_listed_at""", (ticker, scope)).fetchall()
    own: dict[tuple[int, str], Decimal] = {}
    prev: dict[tuple[int, str], Decimal] = {}
    for doc_id, year, period in rows:
        rec = _record(conn, doc_id)
        if rec is None:
            continue
        f = Facts(doc_id, rec)
        if f.template is None:
            continue
        if (v := f.metric("IS", "npat_parent", "q_cur").value) is not None:
            own[(year, period)] = v
        if (v := f.metric("IS", "npat_parent", "q_prev_year").value) is not None:
            prev[(year - 1, period)] = v
    return prev | own


SOURCE_NAMES = {"vietstock": "Vietstock", "hose": "HOSE", "upload": "tệp tải lên"}


def first_seen(listed, source: str, published) -> tuple:
    """Lúc BCTC xuất hiện công khai sớm nhất và nơi xuất hiện: giờ nguồn của tài liệu đăng hoặc giờ HOSE đăng (giờ
    công bố chính thức), lấy cái sớm hơn."""
    if published is not None and (listed is None or published < listed):
        return published, "HOSE"
    return listed, SOURCE_NAMES.get(source, source)


def card_for(conn: psycopg.Connection, document_id: int) -> tuple[Card, dict] | None:
    """(thẻ, thông tin tài liệu) hoặc None nếu chưa có kết quả đọc."""
    row = conn.execute(
        """SELECT d.ticker, c.name, d.fiscal_year, d.fiscal_period, d.scope, d.doc_type, d.status, d.audit_status,
                  d.source_listed_at, d.processed_at, d.source_url, d.title_raw, d.published_at, d.source
           FROM documents d JOIN companies c ON c.ticker = d.ticker WHERE d.id = %s""", (document_id,)).fetchone()
    rec = _record(conn, document_id)
    if row is None or rec is None:
        return None
    ticker, name, year, period, scope, doc_type, status, audit, listed, processed, url, title, published, source = row
    first_at, first_source = first_seen(listed, source, published)
    ev = document_evidence(conn, document_id)
    plans = {m: (v, url) for m, v, url in conn.execute(
        "SELECT metric, value, source_url FROM agm_plans WHERE ticker = %s AND fiscal_year = %s", (ticker, year))}
    card = build_card(document_id, ticker, year, period, rec, npat_history(conn, ticker, scope),
                      ev if ev is not None and ev.peers else None, plans)
    s = rec.get("summary", {})
    info = {"ticker": ticker, "name": name, "year": year, "period": period, "scope": scope, "doc_type": doc_type,
            "status": status, "published": status in PUBLISHABLE,
            "reviewed": {"fs_semiannual": "Đã soát xét", "fs_annual": "Đã kiểm toán"}.get(doc_type, "Chưa soát xét"),
            "listed_at": listed, "processed_at": processed, "source_url": url, "title": title,
            "source": SOURCE_NAMES.get(source, source), "first_at": first_at, "first_source": first_source,
            "gate": (s.get("gate_checks", 0) - s.get("gate_failed", 0), s.get("gate_checks", 0)),
            "manual_fixes": len(rec.get("manual_fixes", [])),
            "explanation": explanation(conn, ticker, year, period, scope)}
    return card, info


def explanation(conn: psycopg.Connection, ticker: str, year: int, period: str, scope: str) -> dict | None:
    """Công văn giải trình kết quả kinh doanh của công ty cho cùng kỳ (ưu tiên cùng phạm vi BCTC), bản đăng sau cùng."""
    row = conn.execute(
        """SELECT title_raw, source_url FROM documents
           WHERE ticker = %s AND fiscal_year = %s AND fiscal_period = %s AND doc_type = 'explanation'
             AND owner_user_id IS NULL AND duplicate_of IS NULL
           ORDER BY (scope = %s) DESC, source_listed_at DESC NULLS LAST LIMIT 1""",
        (ticker, year, period, scope)).fetchone()
    return {"title": row[0].strip(), "url": row[1]} if row else None


def quarter_document(conn: psycopg.Connection, ticker: str, year: int, period: str) -> int | None:
    """BCTC quý dùng cho thẻ: ưu tiên hợp nhất (công ty có công ty con) rồi tới BCTC duy nhất, bản đăng sau cùng."""
    row = conn.execute(
        """SELECT id FROM documents
           WHERE ticker = %s AND fiscal_year = %s AND fiscal_period = %s AND doc_type = 'fs_quarter'
             AND content_kind = 'full' AND scope IN ('consolidated', 'standalone') AND NOT is_amended
             AND owner_user_id IS NULL AND duplicate_of IS NULL
           ORDER BY (processed_at IS NOT NULL) DESC, (scope = 'consolidated') DESC, source_listed_at DESC LIMIT 1""",
        (ticker, year, period)).fetchone()
    return row[0] if row else None


def growth(card: Card) -> dict:
    """Nhóm và % thay đổi LNST công ty mẹ quý này so với cùng kỳ, để xếp hạng. % chỉ tính khi cả hai kỳ đều lãi (lỗ
    thì xếp theo nhóm, không in %, cùng quy tắc với change_text)."""
    np = next((m for m in card.metrics if m.key == "npat_parent"), None)
    cur = np.q_cur.value if np else None
    prev = np.q_prev_year.value if np else None
    if cur is None or prev is None:
        return {"group": "unknown", "pct": None}
    if cur > 0 and prev > 0:
        pct = float((cur - prev) / prev * 100)
        return {"group": "up" if pct >= 0 else "down", "pct": pct}
    if prev <= 0 < cur:
        return {"group": "to_profit", "pct": None}
    if cur <= 0 < prev:
        return {"group": "to_loss", "pct": None}
    return {"group": "loss", "pct": None}


def season(conn: psycopg.Connection, year: int, period: str) -> list[dict]:
    """Bảng mùa BCTC: mỗi công ty đang theo dõi một dòng, kèm thẻ nếu BCTC đã đọc."""
    out = []
    for ticker, name, kind in conn.execute("SELECT ticker, name, template FROM companies WHERE tracked"
                                           " ORDER BY ticker").fetchall():
        doc_id = quarter_document(conn, ticker, year, period)
        item = {"ticker": ticker, "name": name, "kind": kind, "document_id": doc_id, "card": None, "info": None}
        if doc_id is not None:
            got = card_for(conn, doc_id)
            if got is not None:
                item["card"], item["info"] = got
                item["growth"] = growth(item["card"])
                item["flag_keys"] = [fl.key for fl in item["card"].flags]
            else:
                item["info"] = {"status": conn.execute("SELECT status FROM documents WHERE id = %s",
                                                       (doc_id,)).fetchone()[0], "published": False}
        out.append(item)
    return out
