"""Dòng lệnh cho pipeline trích xuất.

    python -m services.extraction run --tickers FPT --year 2026 --period Q2
    python -m services.extraction run --doc-id 12
    python -m services.extraction show --doc-id 12
    python -m services.extraction evidence --year 2026 --period Q2
    python -m services.extraction verify --year 2026 --period Q2
    python -m services.extraction cost
"""

from __future__ import annotations

import argparse
import sys

from services.db import connect
from services.extraction.pipeline import PIPELINE_VER, extract_document, recheck_document, reread_document
from services.llm import VisionClient, cost_usd


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
            conn.commit()   # ghi ngay từng tài liệu, không để cả đợt chạy trong một transaction
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
            for r in rec.get("reextracts", []):
                print(f"    chép lại {r['statement']} trang {r['pages']}: {r['rows_before']} -> {r['rows_after']} dòng, "
                      f"lệch {r['failed_before']} -> {r['failed_after']} ({'giữ bản mới' if r['kept'] else 'giữ bản cũ'})")
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


def cmd_evidence(args) -> None:
    from services.extraction.evidence import STATUS_LABELS, document_evidence
    with connect() as conn:
        ids = args.doc_id or _period_ids(conn, args.year, args.period)
        total = {k: 0 for k in STATUS_LABELS}
        for doc_id in ids:
            ev = document_evidence(conn, doc_id)
            if ev is None:
                continue
            ticker = conn.execute("SELECT ticker FROM documents WHERE id = %s", (doc_id,)).fetchone()[0]
            n = ev.counts()
            for k, v in n.items():
                total[k] += v
            cells = sum(n.values())
            checked = cells - n["none"] - n["restated"]
            peers = ", ".join(f"{p}" for _, p, _ in ev.peers) or "không có kỳ liền kề"
            print(f"[{doc_id}] {ticker}: {cells} ô, đã kiểm {checked} ({checked / cells:.0%}); khớp giữa các kỳ "
                  f"{n['period'] + n['both']}; khác giữa hai BCTC {n['differs']}; cần xem lại {n['conflict']}; "
                  f"trình bày lại {n['restated']} (đối chiếu: {peers})")
            for pc in ev.period_checks:
                if not pc.passed and (args.all or pc.suspect_misread):
                    tag = "TRÌNH BÀY LẠI" if pc.restated else ("CẦN XEM" if pc.suspect_misread else "KHÁC")
                    print(f"    {tag} {pc.kind} {pc.statement} "
                          f"{ev.cells.labels.get((pc.statement, pc.key), pc.key)[:50]} [{pc.key}] {pc.column}: "
                          f"{pc.later:,.0f} vs {pc.expected:,.0f} (lệch {pc.diff:,.0f})")
        cells = sum(total.values())
        if cells:
            print("Tổng: " + "; ".join(f"{STATUS_LABELS[k]} {v} ({v / cells:.0%})" for k, v in total.items()))


def _period_ids(conn, year: int, period: str) -> list[int]:
    return [r[0] for r in conn.execute(
        "SELECT id FROM documents WHERE fiscal_year = %s AND fiscal_period = %s"
        " AND scope IN ('consolidated', 'standalone') AND processed_at IS NOT NULL ORDER BY ticker",
        (year, period)).fetchall()]


def cmd_verify(args) -> None:
    from services.extraction.verify import cells_to_verify, decide, verify_document
    from services.extraction.pipeline import _finalize, _load_record
    if args.redecide:
        with connect() as conn:
            for doc_id in args.doc_id or _period_ids(conn, args.year, args.period):
                rec = _load_record(conn, doc_id)
                if not rec.get("cell_verifications"):
                    continue
                decide(conn, doc_id, rec)
                _finalize(conn, rec)
                conn.commit()
                for e in rec["cell_verifications"]:
                    if not e["same"]:
                        print(f"[{doc_id}] {rec['ticker']} {'SỬA' if e['applied'] else 'khác, không giữ'} "
                              f"{e['statement']} {e['label'][:40]} [{e['key']}] {e['column_kind']}: {e['before']} -> {e['after']}")
        return
    client = VisionClient()
    with connect() as conn:
        todo = cells_to_verify(conn, args.doc_id or _period_ids(conn, args.year, args.period))
        print(f"{sum(len(v) for v in todo.values())} ô cần đọc lại trên {len(todo)} tài liệu")
        for doc_id, cells in sorted(todo.items()):
            ticker, period = conn.execute("SELECT ticker, fiscal_period FROM documents WHERE id = %s", (doc_id,)).fetchone()
            added = verify_document(conn, doc_id, cells, client)
            conn.commit()
            print(f"[{doc_id}] {ticker} {period}: đọc lại {len(added)}/{len(cells)} ô")
            for e in added:
                mark = "giữ nguyên" if e["same"] else ("SỬA" if e["applied"] else "khác, không giữ")
                print(f"    {mark} {e['statement']} {e['label'][:40]} [{e['key']}] {e['column_kind']}: "
                      f"{e['before']} -> {e['after']}")
    u = client.usage
    cost = cost_usd(client.cfg.model, u.input_tokens, u.output_tokens)
    print(f"Tổng: {u.calls} lần gọi, {u.input_tokens:,} token vào, {u.output_tokens:,} token ra"
          + (f", khoảng {cost:.2f} USD" if cost is not None else ""))


def cmd_fix(args) -> None:
    from services.extraction.verify import apply_manual_fix
    with connect() as conn:
        e = apply_manual_fix(conn, args.doc_id, args.statement, args.row, args.column, args.value, args.by, args.note)
        conn.commit()
        print(f"[{args.doc_id}] {e['statement']} dòng {e['row']} ({e['label']}) {e['column_kind']}: "
              f"{e['before']} -> {e['after']}")


def cmd_approve(args) -> None:
    from services.extraction.verify import approve_document
    with connect() as conn:
        status = approve_document(conn, args.doc_id, None, args.by, args.note)
        conn.commit()
        print(f"[{args.doc_id}] -> {status}")


def cmd_cost(args) -> None:
    """Chi phí gọi mô hình đã ghi trong các bản ghi trích xuất. Mỗi tài liệu chỉ giữ bản ghi mới nhất, nên các lần
    chạy bị ghi đè không được tính; bản ghi cũ chưa có số liệu theo bước."""
    import json
    from services.ingestion.registry import raw_data_dir
    steps: dict[str, list[float]] = {}
    total = [0, 0, 0, 0.0]
    docs = 0
    for f in (raw_data_dir() / "extracted").glob("*/*.json"):
        r = json.loads(f.read_text(encoding="utf-8"))
        u = r.get("usage") or {}
        docs += 1
        total[0] += u.get("calls", 0); total[1] += u.get("input_tokens", 0); total[2] += u.get("output_tokens", 0)
        total[3] += cost_usd(r.get("model"), u.get("input_tokens", 0), u.get("output_tokens", 0)) or 0
        known = 0
        for step, su in (r.get("usage_by_step") or {}).items():
            a = steps.setdefault(step, [0, 0, 0, 0.0])
            a[0] += su["calls"]; a[1] += su["input_tokens"]; a[2] += su["output_tokens"]
            a[3] += cost_usd(r.get("model"), su["input_tokens"], su["output_tokens"]) or 0
            known += su["calls"]
        if u.get("calls", 0) > known:
            a = steps.setdefault("(chưa ghi theo bước)", [0, 0, 0, 0.0])
            k = {key: u.get(key, 0) - sum(s.get(key, 0) for s in (r.get("usage_by_step") or {}).values())
                 for key in ("calls", "input_tokens", "output_tokens")}
            a[0] += k["calls"]; a[1] += k["input_tokens"]; a[2] += k["output_tokens"]
            a[3] += cost_usd(r.get("model"), k["input_tokens"], k["output_tokens"]) or 0
    print(f"{docs} bản ghi; {total[0]} lần gọi, {total[1]:,} token vào, {total[2]:,} token ra, khoảng {total[3]:.2f} USD")
    for step, (calls, ti, to, usd) in sorted(steps.items(), key=lambda x: -x[1][3]):
        print(f"  {step:<24} {calls:>5} lần gọi {ti:>12,} vào {to:>11,} ra  {usd:>7.2f} USD")


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

    rr = sub.add_parser("reread", help="Leo thang cho ràng buộc bị lệch: đọc lại ô, rồi chép lại báo cáo theo từng trang")
    rr.add_argument("--doc-id", type=int, nargs="+", required=True)
    rr.set_defaults(func=cmd_reread)

    s = sub.add_parser("show", help="In kết quả kiểm tra ràng buộc")
    s.add_argument("--doc-id", type=int, nargs="+", required=True)
    s.add_argument("--all", action="store_true", help="In cả các phép kiểm tra đạt")
    s.set_defaults(func=cmd_show)

    e = sub.add_parser("evidence", help="Bằng chứng từng ô: cộng tổng và đối chiếu giữa các kỳ (không gọi mô hình)")
    e.add_argument("--doc-id", type=int, nargs="+")
    e.add_argument("--year", type=int)
    e.add_argument("--period")
    e.add_argument("--all", action="store_true", help="In cả các lệch do trình bày lại")
    e.set_defaults(func=cmd_evidence)

    v = sub.add_parser("verify", help="Đọc lại riêng các ô lệch cần xem lại giữa hai BCTC, trên cả hai bản")
    v.add_argument("--doc-id", type=int, nargs="+")
    v.add_argument("--year", type=int)
    v.add_argument("--period")
    v.add_argument("--redecide", action="store_true", help="Chỉ chọn lại số đọc lại nào được giữ, không gọi mô hình")
    v.set_defaults(func=cmd_verify)

    f = sub.add_parser("fix", help="Sửa tay một ô sau khi đối chiếu ảnh gốc (có ghi lại)")
    f.add_argument("--doc-id", type=int, required=True)
    f.add_argument("--statement", required=True, choices=["BS", "IS", "CF"])
    f.add_argument("--row", type=int, required=True, help="Vị trí dòng trong bản chép (bắt đầu từ 0)")
    f.add_argument("--column", required=True, help="end_period, begin_year, q_cur, ytd_cur...")
    f.add_argument("--value", required=True, help="Số nguyên văn như in trên BCTC")
    f.add_argument("--by", required=True, help="Người sửa")
    f.add_argument("--note", default="")
    f.set_defaults(func=cmd_fix)

    a = sub.add_parser("approve", help="Duyệt xuất bản BCTC còn lệch sau khi đối chiếu ảnh gốc (có ghi lại)")
    a.add_argument("--doc-id", type=int, required=True)
    a.add_argument("--by", required=True, help="Người duyệt")
    a.add_argument("--note", required=True, help="Vì sao chỗ lệch còn lại không phải do đọc sai")
    a.set_defaults(func=cmd_approve)

    c = sub.add_parser("cost", help="Chi phí gọi mô hình theo bước, từ các bản ghi đã lưu")
    c.set_defaults(func=cmd_cost)

    args = p.parse_args(argv)
    try:
        args.func(args)
    except RuntimeError as e:   # lỗi cấu hình (thiếu API key, chưa chọn mô hình...)
        sys.exit(f"Lỗi: {e}")


if __name__ == "__main__":
    main()
