"""Ước lượng số ô đọc sai chưa bên nào phát hiện, theo phương pháp bắt-thả-bắt lại (Lincoln-Petersen, hiệu chỉnh Chapman).

    python eval/capture_recapture.py [--listed-before 2026-10-19] [--verbose]

Hai "lưới" bắt lỗi: A = phép kiểm (ràng buộc kế toán trong BCTC và đối chiếu với BCTC kỳ khác), B = người đọc thứ hai
(mô hình khác hãng chép lại báo cáo). Với mỗi ô đã biết là đọc sai (người sửa tay sau khi xem ảnh, hoặc lần đọc lại tự
động đã sửa đúng), đặt lại số sai ban đầu vào bản ghi rồi hỏi: A có báo ô đó không, B có đọc ra số khác số sai không.
n1 = số lỗi A bắt, n2 = số lỗi B bắt, m = số lỗi cả hai cùng bắt; N = (n1+1)(n2+1)/(m+1) - 1.

Giả định: với mỗi lỗi, A bắt và B bắt là hai biến cố độc lập. Lỗi khó với cả hai bên (chữ số dưới con dấu, ảnh 72 dpi)
làm hai bên phụ thuộc dương nên N bị ước lượng thấp: kết quả là cận dưới. Lỗi được sửa bằng cách chép lại cả báo cáo
không có danh sách từng ô nên không nằm trong phép đếm.
"""

from __future__ import annotations

import argparse
import copy
import math
import sys
from collections import Counter

from eval.fault_injection import FLAGGED, gate_failures
from eval.repair import truth_cells
from services.db import connect
from services.extraction.evidence import cells_of, document_evidence, same_reading, second_cells, second_value
from services.extraction.numbers import normalize_code
from services.extraction.pipeline import _check, _load_record
from services.extraction.repair import _cells_of


def _flagged_by_checks(conn, d: int, broken: dict, cell: tuple[str, int, str], base_fail: set, loader) -> bool:
    st, row, col = cell
    extracted, statements, sep, template, checks = _check(copy.deepcopy(broken))
    ex = next((e for e in extracted if e.statement == st), None)
    code = normalize_code(ex.items[row].code) if ex and row < len(ex.items) else None
    for c in checks:
        if template and code and c.gate and not c.passed and (c.rule_id, c.column_kind) not in base_fail:
            if (st, code, col) in set(_cells_of(c, template, statements)):
                return True
    ev = document_evidence(conn, d, load=lambda x: broken if x == d else loader(x))
    if ev is None:
        return False
    keys = ev.cells.item_keys.get(st, [])
    key = keys[row] if row < len(keys) else None
    return bool(key) and ev.status.get((st, key, col), {}).get("status") in FLAGGED


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--listed-before", help="chỉ tính BCTC Vietstock đăng trước ngày này (YYYY-MM-DD)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    tally = Counter()
    cache: dict[int, dict | None] = {}

    def loader(x: int):
        if x not in cache:
            try:
                cache[x] = _load_record(conn, x)
            except RuntimeError:
                cache[x] = None
        return cache[x]

    with connect() as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM documents WHERE owner_user_id IS NULL AND status IN ('verified', 'approved') "
            "AND (%s::date IS NULL OR source_listed_at < %s::date) ORDER BY id", (args.listed_before, args.listed_before))]
        for d in ids:
            record = loader(d)
            if not record or not record.get("second_read"):
                continue
            base_fail = gate_failures(copy.deepcopy(record))
            for (st, row, col), (wrong, right, source) in truth_cells(record).items():
                digits = lambda v: "".join(ch for ch in str(v or "") if ch.isdigit())
                if not wrong or not digits(wrong) or digits(wrong) == digits(right):
                    continue        # chỉ sửa dấu phân cách hoặc dấu âm trong chuỗi, cùng dãy chữ số: không phải đọc sai số
                broken = copy.deepcopy(record)
                broken["raw"][st]["rows"][row]["values"][col] = wrong
                a = _flagged_by_checks(conn, d, broken, (st, row, col), base_fail, loader)
                mine = cells_of(d, "", broken)
                keys = mine.item_keys.get(st, [])
                key = keys[row] if row < len(keys) else None
                first = mine.row(st, key).get(col) if key else None
                theirs = second_cells(d, "", broken)
                b_val = second_value(mine, theirs, (st, key, col), broken.get("doc_type")) if key and theirs else None
                if b_val is None and theirs is not None and key and theirs.row(st, key) and not digits(right):
                    b = True        # đúng ra ô để trống, người đọc thứ hai cũng đọc trống
                else:
                    b = first is not None and b_val is not None and not same_reading(first, b_val)
                tally["lỗi"] += 1
                tally["A"] += a
                tally["B"] += b
                tally["A và B"] += a and b
                tally["không bên nào"] += not a and not b
                if args.verbose and not (a and b):
                    print(f"  [{d} {record['ticker']}] {st} dòng {row} {col}: {wrong} -> {right} ({source}); "
                          f"A={'có' if a else 'không'} B={'có' if b else 'không'}")
    n1, n2, m = tally["A"], tally["B"], tally["A và B"]
    print(f"{tally['lỗi']} ô đã biết là đọc sai; phép kiểm (A) bắt {n1}, người đọc thứ hai (B) bắt {n2}, cả hai {m}, "
          f"không bên nào {tally['không bên nào']}")
    if m:
        n_hat = (n1 + 1) * (n2 + 1) / (m + 1) - 1
        var = (n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m) / ((m + 1) ** 2 * (m + 2))
        seen = n1 + n2 - m
        print(f"Chapman: tổng số lỗi ước lượng {n_hat:.1f} (khoảng tin cậy 95%: {n_hat - 1.96 * math.sqrt(var):.1f} - "
              f"{n_hat + 1.96 * math.sqrt(var):.1f}); hai lưới đã thấy {seen}; chưa bên nào thấy khoảng "
              f"{n_hat - seen:.1f} (cận dưới, xem giả định)")


if __name__ == "__main__":
    main()
