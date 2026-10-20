"""Đọc công văn giải trình kết quả kinh doanh và đối chiếu với BCTC đã kiểm chứng (services/analyst/explanations.py).

    python eval/explanations.py --limit 5 [--doc-id 13248 ...] [--verbose]

Kết quả đọc của mô hình lưu ở Data/raw/explanations/<mã tài liệu>.json: chạy lại chỉ chấm lại, không gọi mô hình.
Đếm theo từng phép đối chiếu: khớp, lệch, khớp chiều (công ty chỉ nói tăng/giảm), không kiểm được.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from services.analyst.explanations import PROMPT, SCHEMA, check_section
from services.db import connect
from services.extraction.pipeline import LOCATE_LONG_SIDE, _load_record
from services.extraction.sources import candidates, open_pdf, render_page
from services.ingestion.registry import raw_data_dir
from services.metrics.card import Facts

MAX_PAGES = 6
PAGE_LONG_SIDE = 1600       # công văn chữ to hơn bảng số: ảnh vừa phải là đọc được


def facts_for(conn, ticker: str, year: int, period: str, scope: str, period_kind: str):
    """BCTC đã kiểm chứng ứng với một phần của công văn: quý/lũy kế -> BCTC quý cùng kỳ; bán niên -> BCTC bán niên (phần
    nói về quý 2 thì BCTC quý 2); năm -> BCTC năm. Phần riêng (công ty mẹ): chưa có."""
    if scope == "separate":
        return None
    if period == "H1" and period_kind == "quarter":
        doc_type, per = "fs_quarter", "Q2"
    elif period == "H1":
        doc_type, per = "fs_semiannual", "H1"
    elif period == "FY":
        doc_type, per = "fs_annual", "FY"
    else:
        doc_type, per = "fs_quarter", period
    row = conn.execute(
        """SELECT id FROM documents WHERE ticker = %s AND fiscal_year = %s AND fiscal_period = %s AND doc_type = %s
             AND content_kind = 'full' AND scope IN ('consolidated', 'standalone') AND status IN ('verified', 'approved')
             AND owner_user_id IS NULL AND duplicate_of IS NULL AND NOT is_amended
           ORDER BY (scope = 'consolidated') DESC LIMIT 1""", (ticker, year, per, doc_type)).fetchone()
    if row is None:
        return None
    return Facts(row[0], _load_record(conn, row[0]))


def read_letter(client, path) -> dict:
    doc = open_pdf(candidates(path)[0])
    images = [(f"Trang {p}", render_page(doc, p, PAGE_LONG_SIDE)) for p in range(1, min(doc.page_count, MAX_PAGES) + 1)]
    return client.json_from_images(PROMPT, images, SCHEMA, "explanation_read")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--doc-id", type=int, nargs="+")
    ap.add_argument("--limit", type=int, help="số công văn tối đa (mới nhất trước)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    out_dir = raw_data_dir() / "explanations"
    out_dir.mkdir(parents=True, exist_ok=True)
    client = None
    tally, letters = Counter(), Counter()
    with connect() as conn:
        rows = conn.execute(
            """SELECT d.id, d.ticker, d.fiscal_year, d.fiscal_period, f.storage_key FROM documents d
               JOIN LATERAL (SELECT storage_key FROM document_files WHERE document_id = d.id ORDER BY downloaded_at DESC
                             LIMIT 1) f ON true
               WHERE d.doc_type = 'explanation' AND d.duplicate_of IS NULL AND d.owner_user_id IS NULL
                 AND d.fiscal_year >= 2025 AND (%s::bigint[] IS NULL OR d.id = ANY(%s))
                 AND d.ticker IN (SELECT ticker FROM companies WHERE tracked)
               ORDER BY d.fiscal_year DESC, d.fiscal_period DESC, d.ticker""", (args.doc_id, args.doc_id)).fetchall()
        if args.limit:
            rows = rows[:args.limit]
        for doc_id, ticker, year, period, key in rows:
            cache = out_dir / f"{doc_id}.json"
            if cache.exists():
                data = json.loads(cache.read_text(encoding="utf-8"))
            else:
                if client is None:
                    from services.llm import VisionClient
                    client = VisionClient()
                data = read_letter(client, raw_data_dir() / key)
                cache.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            letters["công văn"] += 1
            print(f"[{doc_id}] {ticker} {period}/{year}: {len(data['sections'])} phần")
            for sec in data["sections"]:
                facts = facts_for(conn, ticker, year, period, sec["scope"], sec["period_kind"])
                res = check_section(sec, facts)
                for c in res.checks:
                    kind = "câu chính" if c.what.startswith(("lợi nhuận", "doanh thu", "% thay đổi")) else (
                        "cả phần" if c.what == "cả phần" else "nguyên nhân")
                    tally[(kind, c.verdict)] += 1
                    if args.verbose:
                        print(f"    {res.scope}/{res.period_kind} · {c.what}: {c.verdict}"
                              + (f" | công ty: {c.stated}" if c.stated else "") + (f" | BCTC: {c.bctc}" if c.bctc else "")
                              + (f" ({c.note})" if c.note else ""))
    print(f"\n{letters['công văn']} công văn")
    for kind in ("câu chính", "nguyên nhân", "cả phần"):
        c = {v: n for (k, v), n in tally.items() if k == kind}
        if c:
            print(f"  {kind}: " + ", ".join(f"{v} {n}" for v, n in sorted(c.items(), key=lambda x: -x[1])))
    if client is not None:
        print(f"Chi phí gọi mô hình: {client.usage.usd:.3f} USD")


if __name__ == "__main__":
    main()
