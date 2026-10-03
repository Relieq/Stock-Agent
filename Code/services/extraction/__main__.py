"""Dòng lệnh cho pipeline trích xuất.

    python -m services.extraction run --tickers FPT --year 2026 --period Q2
    python -m services.extraction run --doc-id 12
    python -m services.extraction show --doc-id 12
"""

from __future__ import annotations

import argparse
import sys

from services.db import connect
from services.extraction.pipeline import PIPELINE_VER, extract_document, recheck_document, reread_document
from services.llm import VisionClient


def _select(conn, args) -> list[tuple[int, str, str]]:
    if args.doc_id:
        return conn.execute("SELECT id, ticker, title_raw FROM documents WHERE id = ANY(%s)", (args.doc_id,)).fetchall()
    q = ["SELECT id, ticker, title_raw FROM documents d WHERE status IN ('downloaded', 'needs_review', 'failed')",
         "AND content_kind = 'full' AND EXISTS (SELECT 1 FROM document_files f WHERE f.document_id = d.id)"]
    params: list[object] = []
    for col, val in (("fiscal_year", args.year), ("fiscal_period", args.period), ("doc_type", args.doc_type),
                     ("scope", args.scope)):
        if val:
            q.append(f"AND {col} = %s")
            params.append(val)
    if args.tickers:
        q.append("AND ticker = ANY(%s)")
        params.append([t.strip().upper() for t in args.tickers.split(",")])
    q.append("ORDER BY ticker, scope LIMIT %s")
    params.append(args.limit)
    return conn.execute(" ".join(q), params).fetchall()


def cmd_run(args) -> None:
    client = VisionClient()
    print(f"Mô hình: {client.cfg.provider}/{client.cfg.model}; pipeline {PIPELINE_VER}")
    with connect() as conn:
        docs = _select(conn, args)
        print(f"{len(docs)} tài liệu")
        for doc_id, ticker, title in docs:
            print(f"- [{doc_id}] {ticker} {title}")
            try:
                rec = extract_document(conn, doc_id, client)
            except Exception as e:
                conn.execute("UPDATE documents SET status = 'failed' WHERE id = %s", (doc_id,))
                conn.commit()
                print(f"    lỗi: {e}")
                continue
            s = rec["summary"]
            pages = {k: v for k, v in next(c for c in rec["candidates"] if c["name"] == rec["chosen"])["statement_pages"].items()}
            print(f"    trang: {pages}; mẫu: {rec['template_ver']}; ràng buộc bắt buộc: "
                  f"{s['gate_checks'] - s['gate_failed']}/{s['gate_checks']} đạt; -> {rec['status']}")
    u = client.usage
    print(f"Tổng: {u.calls} lần gọi, {u.input_tokens:,} token vào, {u.output_tokens:,} token ra, {u.seconds:.0f} giây")


def cmd_recheck(args) -> None:
    with connect() as conn:
        for doc_id in args.doc_id:
            rec = recheck_document(conn, doc_id)
            s = rec["summary"]
            print(f"[{doc_id}] {rec['ticker']}: mẫu {rec['template_ver']}; ràng buộc bắt buộc "
                  f"{s['gate_checks'] - s['gate_failed']}/{s['gate_checks']} đạt; "
                  f"chưa bắt buộc lệch {s['info_failed']}; -> {rec['status']}"
                  + (f"; mã in trùng: {rec['duplicate_codes']}" if rec.get("duplicate_codes") else ""))


def cmd_reread(args) -> None:
    client = VisionClient()
    with connect() as conn:
        for doc_id in args.doc_id:
            rec = reread_document(conn, doc_id, client)
            s = rec["summary"]
            print(f"[{doc_id}] {rec['ticker']}: ràng buộc bắt buộc {s['gate_checks'] - s['gate_failed']}/{s['gate_checks']} "
                  f"đạt -> {rec['status']}")
            for r in rec.get("rereads", [])[-20:]:
                mark = "đổi" if r["before"] != r["after"] else "giữ"
                print(f"    {mark} {r['statement']} {r['code']} {r['column_kind']}: {r['before']} -> {r['after']}")


def cmd_show(args) -> None:
    with connect() as conn:
        for doc_id in args.doc_id:
            rows = conn.execute(
                """
                SELECT v.rule_id, v.column_kind, v.passed, v.lhs, v.rhs, v.details->>'gate'
                FROM validations v JOIN document_files f ON f.id = v.file_id
                WHERE f.document_id = %s ORDER BY v.passed, v.rule_id, v.column_kind
                """,
                (doc_id,),
            ).fetchall()
            print(f"Tài liệu {doc_id}: {len(rows)} phép kiểm tra")
            for rule_id, col, passed, lhs, rhs, gate in rows:
                if passed and not args.all:
                    continue
                mark = "đạt " if passed else "LỆCH"
                print(f"  {mark} {rule_id:<16} {col:<22} {lhs:>22,.0f} {rhs:>22,.0f}  "
                      f"lệch {lhs - rhs:>18,.0f}{'' if gate == 'true' else '  (chưa bắt buộc)'}")


def main(argv: list[str] | None = None) -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="python -m services.extraction", description="Đọc và kiểm chứng BCTC")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="Trích xuất các tài liệu đã tải")
    r.add_argument("--doc-id", type=int, nargs="+")
    r.add_argument("--year", type=int)
    r.add_argument("--period")
    r.add_argument("--doc-type", default="fs_quarter")
    r.add_argument("--scope", help="consolidated / separate / standalone")
    r.add_argument("--tickers")
    r.add_argument("--limit", type=int, default=5)
    r.set_defaults(func=cmd_run)

    rc = sub.add_parser("recheck", help="Kiểm tra lại từ kết quả đã lưu, không gọi mô hình")
    rc.add_argument("--doc-id", type=int, nargs="+", required=True)
    rc.set_defaults(func=cmd_recheck)

    rr = sub.add_parser("reread", help="Đọc lại các ô thuộc ràng buộc bị lệch")
    rr.add_argument("--doc-id", type=int, nargs="+", required=True)
    rr.set_defaults(func=cmd_reread)

    s = sub.add_parser("show", help="In kết quả kiểm tra ràng buộc")
    s.add_argument("--doc-id", type=int, nargs="+", required=True)
    s.add_argument("--all", action="store_true", help="In cả các phép kiểm tra đạt")
    s.set_defaults(func=cmd_show)

    args = p.parse_args(argv)
    try:
        args.func(args)
    except RuntimeError as e:   # lỗi cấu hình (thiếu API key, chưa chọn mô hình...)
        sys.exit(f"Lỗi: {e}")


if __name__ == "__main__":
    main()
