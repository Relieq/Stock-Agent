"""Người đọc thứ hai: chép lại các báo cáo của BCTC đã đọc bằng nhà cung cấp khác hãng với lần đọc đầu, rồi so từng ô
với số đang lưu. Lần đọc thứ hai lưu vào bản ghi (record["second_read"], như bước đọc lần hai trong bộ canh,
services/extraction/second_read.py), không thay số của lần đọc đầu.

    python eval/second_read.py run [--doc-id 8 10] [--limit 5]   # gọi mô hình, chép lại mọi báo cáo
    python eval/second_read.py import                            # nạp Data/raw/second_read/<id>.json cũ vào bản ghi
    python eval/second_read.py compare [--list 50]               # so từng ô, không gọi mô hình

Bộ canh chỉ chép lại báo cáo còn ô chưa kiểm được; ở đây chép lại cả báo cáo để đo hai lần đọc trùng nhau bao nhiêu
trên các ô đã có phép kiểm xác nhận (ô có đáp án gần đúng). Phép cộng không thấy được lỗi đổi chỗ hai dòng cùng thuộc
một tổng (cấy 500 lỗi như vậy, phép kiểm bắt buộc trong chính BCTC chỉ bắt được 42%), và không phủ các dòng không có
phép cộng nào (lãi trên cổ phiếu, mục ngoài bảng của ngân hàng). Một người đọc khác hãng hầu như không mắc đúng lỗi đó,
nên ô hai bên khác nhau là ô cần xem lại; ô hai bên trùng nhau có thêm một bằng chứng độc lập với phép kiểm.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from eval.cell_funnel import NAMES, classify
from services.db import connect
from services.extraction.evidence import cells_of, same_reading, second_cells, second_value
from services.extraction.pipeline import _check_cached, _finalize, _load_record, open_record_pdf
from services.extraction.second_read import read
from services.ingestion.registry import raw_data_dir
from services.llm import VisionClient


def _documents(conn, ids: list[int] | None, listed_before: str | None = None) -> list[tuple[int, str, str]]:
    rows = conn.execute("SELECT id, ticker, fiscal_period || '/' || fiscal_year FROM documents WHERE owner_user_id IS NULL "
                        "AND status IN ('verified', 'approved', 'needs_review') "
                        "AND (%s::date IS NULL OR source_listed_at < %s::date) ORDER BY id",
                        (listed_before, listed_before)).fetchall()
    return [r for r in rows if ids is None or r[0] in ids]


def run(ids: list[int] | None, limit: int | None) -> None:
    client = VisionClient()
    done = 0
    with connect() as conn:
        for d, ticker, period in _documents(conn, ids):
            record = _load_record(conn, d)
            if record.get("second_read"):
                continue
            if limit is not None and done >= limit:
                break
            second = read(record, client, open_record_pdf(conn, record))
            if second is None:
                print("Chỉ cấu hình một nhà cung cấp: không có người đọc thứ hai")
                return
            record["second_read"] = second
            _finalize(conn, record)
            conn.commit()
            done += 1
            print(f"[{d}] {ticker} {period}: {', '.join(second['second_reader'])}, {second['usd']:.4f} USD", flush=True)
    print(f"Xong {done} BCTC, tổng {client.usage.usd:.2f} USD")


def probe(ids: list[int], provider: str) -> None:
    """Đo một người đọc thứ hai khác (ví dụ gpt-5.4-mini khi lần đọc đầu là Haiku) mà không ghi gì: chép lại cả BCTC rồi
    so với các ô đã có xác nhận (nhóm 1-4: phép kiểm; nhóm 8: hai lần đọc trước trùng nhau). Tỷ lệ khác ở nhóm 8 là số ô
    bị đánh dấu nhầm "cần xem lại" có thể gặp khi dùng người đọc này trong bộ canh."""
    client = VisionClient()
    tally: dict[str, Counter] = {"1-4": Counter(), "8": Counter()}
    with connect() as conn:
        for d, ticker, period in _documents(conn, ids):
            record = _load_record(conn, d)
            second = read(record, client, open_record_pdf(conn, record), provider=provider)
            probe_rec = record | {"second_read": second}
            mine, theirs = cells_of(d, period.split("/")[0], record), second_cells(d, period.split("/")[0], probe_rec)
            per_doc = Counter()
            for cat, st, row, col, _, _ in classify(conn, d):
                group = "1-4" if cat <= 4 else "8" if cat == 8 else None
                keys = mine.item_keys.get(st, [])
                key = keys[row] if row < len(keys) else None
                a = mine.row(st, key).get(col) if key else None
                if group is None or a is None:
                    continue
                b = second_value(mine, theirs, (st, key, col), record.get("doc_type"))
                result = "không thấy" if b is None else "trùng" if same_reading(a, b) else "khác"
                tally[group][result] += 1
                per_doc[(group, result)] += 1
                if result == "khác" and group == "8":
                    print(f"    khác nhóm 8: {st} {key} {col}: {a} / {b}")
            print(f"[{d}] {ticker} {period}: {', '.join(second['second_reader'])}, {second['usd']:.4f} USD; nhóm 8 khác "
                  f"{per_doc[('8', 'khác')]}/{sum(v for (g, _), v in per_doc.items() if g == '8')}, nhóm 1-4 khác "
                  f"{per_doc[('1-4', 'khác')]}", flush=True)
    for group, t in tally.items():
        n = t["trùng"] + t["khác"]
        print(f"Nhóm {group}: {sum(t.values()):,} ô; trùng {t['trùng']:,}, khác {t['khác']:,}"
              + (f" ({100 * t['khác'] / n:.1f}% số ô người đọc thấy)" if n else "") + f", không thấy {t['không thấy']:,}")
    print(f"Tổng {client.usage.usd:.3f} USD")


def import_files() -> None:
    """Lần đo đầu (18/10/2026) lưu lần đọc thứ hai ra file riêng; nạp vào bản ghi để bộ canh không đọc lại."""
    n = 0
    with connect() as conn:
        for path in sorted((raw_data_dir() / "second_read").glob("*.json"), key=lambda p: int(p.stem)):
            got = json.loads(path.read_text(encoding="utf-8"))
            record = _load_record(conn, int(path.stem))
            if record.get("second_read"):
                continue
            record["second_read"] = {k: got[k] for k in ("first_reader", "second_reader", "usd", "raw")}
            _finalize(conn, record)
            conn.commit()
            n += 1
    print(f"Đã nạp {n} lần đọc thứ hai vào bản ghi")


def compare_document(conn, d: int, period: str) -> list[dict]:
    """Mọi ô có số ở bản đang lưu: trùng / khác / người đọc thứ hai không thấy, kèm nhóm xác nhận (eval/cell_funnel)."""
    record = _load_record(conn, d)
    if not record.get("second_read"):
        return []
    mine, theirs = cells_of(d, period, record), second_cells(d, period, record)
    other = {k: v for k, v in record.items() if k != "second_read"} | {"raw": record["second_read"]["raw"]}
    cats = {(st, row, col): cat for cat, st, row, col, _, _ in classify(conn, d)}
    gate_ok = not [c for c in _check_cached(other)[4] if c.gate and not c.passed]
    out = []
    for (st, row, col), cat in cats.items():
        keys = mine.item_keys.get(st, [])
        key = keys[row] if row < len(keys) else None
        if key is None:
            continue                # dòng không xác định được khóa
        a = mine.row(st, key).get(col)
        if a is None:
            continue
        b = second_value(mine, theirs, (st, key, col), record.get("doc_type"))
        if b is None:
            result = "không thấy"
        elif a == b:
            result = "trùng"
        elif same_reading(a, b):
            result = "khác đơn vị"      # cùng dãy chữ số, hai lần đọc hiểu đơn vị tính khác nhau
        else:
            result = "khác"
        out.append({"document_id": d, "statement": st, "row": row, "key": key, "column_kind": col, "cat": cat,
                    "mine": str(a), "theirs": None if b is None else str(b), "result": result,
                    "second_gate_ok": gate_ok})
    return out


def compare(list_n: int, listed_before: str | None = None) -> None:
    tally: dict[int, Counter] = {}
    docs, gate_ok, usd = 0, 0, 0.0
    differ = []
    with connect() as conn:
        for d, ticker, period in _documents(conn, None, listed_before):
            rows = compare_document(conn, d, period.split("/")[0])
            if not rows:
                continue
            docs += 1
            gate_ok += rows[0]["second_gate_ok"]
            usd += _load_record(conn, d)["second_read"].get("usd") or 0
            for r in rows:
                tally.setdefault(r["cat"], Counter())[r["result"]] += 1
                if r["result"] == "khác":
                    differ.append((ticker, period, r))
    print(f"{docs} BCTC đã có lần đọc thứ hai ({usd:.2f} USD); người đọc thứ hai tự đạt mọi phép kiểm bắt buộc ở "
          f"{gate_ok}/{docs} BCTC")
    for cat in sorted(tally):
        t = tally[cat]
        n = sum(t.values())
        print(f"  {cat}. {NAMES[cat]}: {n:,} ô; trùng {t['trùng']:,} ({100 * t['trùng'] / n:.1f}%), "
              f"khác {t['khác']:,}, khác đơn vị {t['khác đơn vị']:,}, không thấy {t['không thấy']:,}")
    for ticker, period, r in differ[:list_n]:
        print(f"  khác: {ticker} {period} (doc {r['document_id']}) {r['statement']} {r['key']} {r['column_kind']} "
              f"nhóm {r['cat']}: lưu {r['mine']} / người thứ hai {r['theirs']}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--doc-id", type=int, nargs="+")
    r.add_argument("--limit", type=int)
    sub.add_parser("import")
    pr = sub.add_parser("probe")
    pr.add_argument("--doc-id", type=int, nargs="+", required=True)
    pr.add_argument("--provider", required=True)
    c = sub.add_parser("compare")
    c.add_argument("--list", type=int, default=0, help="in N ô khác nhau đầu tiên")
    c.add_argument("--listed-before", help="chỉ tính BCTC Vietstock đăng trước ngày này (YYYY-MM-DD), để số liệu báo cáo giữ đúng phạm vi đã ghi")
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.doc_id, args.limit)
    elif args.cmd == "probe":
        probe(args.doc_id, args.provider)
    elif args.cmd == "import":
        import_files()
    else:
        compare(args.list, args.listed_before)


if __name__ == "__main__":
    main()
