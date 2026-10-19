"""Đo bộ máy tự định vị ô đọc sai (services/extraction/repair.py) trên các lỗi đã biết, không gọi mô hình.

    python eval/repair.py [--verbose]

Đề kiểm tra lấy từ các bản ghi trích xuất đã lưu:
  * sửa tay (record["manual_fixes"]): người duyệt đối chiếu ảnh gốc, có số cũ và số mới;
  * đọc lại (record["rereads"]) của tài liệu nay đã đạt kiểm chứng/được duyệt: lần đọc lại ra số khác và số đó còn
    nằm trong bản ghi cuối.
Với mỗi tài liệu, trả các ô đó về số sai ban đầu, chạy định vị lỗi rồi so với số đúng. Kết quả theo ô:
  * đúng: đề xuất duy nhất (độ tin cao/vừa) đúng ô, đúng số;
  * cần đọc lại: ô nằm trong một nhóm phương án ngang nhau, có phương án đúng số (đọc lại riêng từng ô sẽ chọn được);
  * sót: không có đề xuất nào cho ô này (ví dụ lỗi không làm lệch phép cộng nào trong chính BCTC đó);
và đề xuất sai: đề xuất cho ô không có trong đề hoặc sai số.
"""

from __future__ import annotations

import argparse
import copy
import sys
from collections import Counter

from services.db import connect
from services.extraction.numbers import normalize_code, parse_amount
from services.extraction.pipeline import _check, _load_record
from services.extraction.evidence import document_evidence
from services.extraction.confusion import count_substitutions, error_pairs
from services.extraction.repair import cross_proposals, localize, rank_group


def truth_cells(record: dict) -> dict[tuple[str, int, str], tuple[str | None, str, str]]:
    """(báo cáo, dòng, cột) -> (số sai ban đầu, số đúng, nguồn). Lấy lần sửa đầu tiên làm số sai, lần cuối làm số đúng."""
    out: dict = {}
    if record.get("status") in ("verified", "approved"):
        for r in record.get("rereads", []):
            if r.get("before") == r.get("after") or r.get("kept") is False:
                continue
            rows = record["raw"].get(r["statement"], {}).get("rows", [])
            idx = next((i for i, row in enumerate(rows) if normalize_code(row.get("code")) == r["code"]), None)
            if idx is None or rows[idx]["values"].get(r["column_kind"]) != r["after"]:
                continue
            key = (r["statement"], idx, r["column_kind"])
            out[key] = (out.get(key, (r["before"],))[0], r["after"], "đọc lại")
    for f in record.get("manual_fixes", []):
        key = (f["statement"], f["row"], f["column_kind"])
        out[key] = (out.get(key, (f["before"],))[0], f["after"], "sửa tay")
    return out


def extracted_code(extracted, key):
    st, row, _ = key
    ex = next((e for e in extracted if e.statement == st), None)
    return ex.items[row].code if ex and row < len(ex.items) else None


def _cells_in_failures(extracted, statements, template) -> set:
    """Các ô thuộc ít nhất một ràng buộc bắt buộc bị lệch trong chính BCTC (lỗi khác chỉ lộ khi đối chiếu BCTC khác)."""
    from services.extraction.repair import _cells_of
    from services.extraction.validate import validate
    if template is None:
        return set()
    return {cell for c in validate(statements, template) if c.gate and not c.passed
            for cell in _cells_of(c, template, statements)}


def evaluate(record: dict, verbose: bool = False, conn=None, table: dict | None = None) -> Counter:
    truth = truth_cells(record)
    tally: Counter = Counter()
    if not truth:
        return tally
    broken = copy.deepcopy(record)
    for (st, row, col), (before, _, _) in truth.items():
        broken["raw"][st]["rows"][row]["values"][col] = before
    extracted, statements, sep, template, _ = _check(broken)
    loc = localize(extracted, statements, sep, template)
    if conn is not None:
        doc_id = record["document_id"]

        def load(d):
            if d == doc_id:
                return broken
            try:
                return _load_record(conn, d)
            except RuntimeError:
                return None
        taken = {(p.statement, p.row, p.column_kind) for p in loc.proposals} |                 {(p.statement, p.row, p.column_kind) for g in loc.ambiguous for p in g}
        loc.ambiguous += cross_proposals(document_evidence(conn, doc_id, load=load), extracted, statements, sep,
                                         template, taken)

    def same(raw_a, raw_b):
        a, b = parse_amount(raw_a, sep), parse_amount(raw_b, sep)
        return a is not None and a == b

    sure = {(p.statement, p.row, p.column_kind): p for p in loc.proposals}
    grouped_list = [q for g in loc.ambiguous for p in g for q in (p, p.partner) if q]
    grouped = {(p.statement, p.row, p.column_kind): p for p in grouped_list}
    involved = _cells_in_failures(extracted, statements, template)
    for key, (before, after, source) in truth.items():
        if parse_amount(before, sep) == parse_amount(after, sep):
            continue        # chỉ khác cách viết (dấu phân tách), bước chuẩn hóa số đã đọc đúng
        code = normalize_code(extracted_code(extracted, key))
        in_scope = (key[0], code, key[2]) in involved
        if key in sure and same(sure[key].after, after):
            result = "đúng"
        elif key in grouped and same(grouped[key].after, after):
            result = "cần đọc lại"
            covers = lambda p: key in {(q.statement, q.row, q.column_kind) for q in (p, p.partner) if q is not None}
            group = next(g for g in loc.ambiguous if any(covers(p) for p in g))
            tally["xếp theo mô hình nhầm: ô đúng đứng đầu"] += covers(rank_group(list(group), table)[0])
        else:
            result = "sót" if in_scope else "ngoài tầm"
        if not in_scope and result != "ngoài tầm":
            result += " (nhờ BCTC kỳ khác)"
        tally[result.split(" (")[0]] += 1
        tally[f"nguồn bằng chứng: {'trong BCTC' if in_scope else 'BCTC kỳ khác'}: {result.split(' (')[0]}"] += 1
        tally[f"{source}: {result}"] += 1
        if verbose:
            p = sure.get(key) or grouped.get(key)
            print(f"  [{record['document_id']} {record['ticker']}] {key} {before} -> {after} ({source}): {result}"
                  + (f"; đề xuất {p.after} ({p.confidence}, {len(p.fixes)} ràng buộc)" if p else ""))
    for p in loc.proposals:
        key = (p.statement, p.row, p.column_kind)
        if key not in truth or not same(p.after, truth[key][1]):
            tally["đề xuất sai"] += 1
            if verbose:
                print(f"  [{record['document_id']} {record['ticker']}] ĐỀ XUẤT SAI {key} {p.before} -> {p.after} "
                      f"({p.confidence}, {p.fixes})")
    tally["nhóm cần đọc lại"] += len(loc.ambiguous)
    tally["ô phải đọc lại"] += sum(len(g) for g in loc.ambiguous)
    return tally


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--listed-before", help="chỉ tính BCTC Vietstock đăng trước ngày này (YYYY-MM-DD), để số liệu báo cáo "
                                            "giữ đúng phạm vi đã ghi")
    args = ap.parse_args()
    total: Counter = Counter()
    docs = 0
    with connect() as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM documents WHERE status IN ('verified', 'approved', 'needs_review') "
            "AND (%s::date IS NULL OR source_listed_at < %s::date) ORDER BY id", (args.listed_before, args.listed_before))]
        records = {}
        for doc_id in ids:
            try:
                records[doc_id] = _load_record(conn, doc_id)
            except RuntimeError:
                continue
        pairs = {d: error_pairs(r) for d, r in records.items()}
        for doc_id, record in records.items():
            # Bảng nhầm học từ lỗi của các BCTC khác, để không chấm điểm trên chính dữ liệu đã học
            table = count_substitutions([p for d, ps in pairs.items() if d != doc_id for p in ps])
            t = evaluate(record, args.verbose, conn, table)
            if t:
                docs += 1
                total += t
    cells = total["đúng"] + total["cần đọc lại"] + total["sót"]
    print(f"{docs} tài liệu, {cells + total['ngoài tầm']} ô đã biết là đọc sai")
    print(f"  ngoài tầm (không phép cộng nào trong BCTC hay đối chiếu kỳ khác chỉ ra): {total['ngoài tầm']}")
    print(f"  trong tầm: {cells}")
    for k in ("đúng", "cần đọc lại", "sót"):
        print(f"  {k:12s} {total[k]:4d}  ({total[k] / cells:.0%})" if cells else "")
    print(f"  đề xuất sai  {total['đề xuất sai']:4d}")
    print(f"  nhóm phương án ngang nhau: {total['nhóm cần đọc lại']}, tổng {total['ô phải đọc lại']} ô phải đọc lại")
    if total["cần đọc lại"]:
        print(f"  trong {total['cần đọc lại']} ô cần đọc lại, xếp theo mô hình nhầm (học từ BCTC khác) đưa ô đúng lên đầu "
              f"{total['xếp theo mô hình nhầm: ô đúng đứng đầu']} lần")
    for k in sorted(k for k in total if ":" in k):
        print(f"    {k}: {total[k]}")


if __name__ == "__main__":
    main()
