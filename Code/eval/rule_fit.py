"""Đo mức khớp của từng ràng buộc kế toán trên mọi BCTC đã đọc (không gọi mô hình).

    python eval/rule_fit.py [--template TT99] [--rule BS_130] [--verbose]

Dùng trước khi đưa một ràng buộc mới vào nhóm bắt buộc: ràng buộc đúng theo mẫu biểu phải khớp trên gần như mọi BCTC có
đủ số hạng. Ràng buộc trượt nhiều nghĩa là khai báo sai (thiếu mã con, sai dấu, mẫu biểu khác) chứ không phải đọc sai;
ràng buộc trượt lẻ tẻ thì xem từng chỗ trượt (--verbose) để phân biệt đọc sai với BCTC in lệch.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict

from services.db import connect
from services.extraction.pipeline import _check_cached, _load_record
from services.extraction.validate import validate


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--template", help="chỉ xét một mẫu (TT200, TT99, TCTD, CTCK)")
    ap.add_argument("--rule", help="chỉ xét ràng buộc có mã bắt đầu bằng chuỗi này")
    ap.add_argument("--verbose", action="store_true", help="in từng chỗ trượt")
    args = ap.parse_args()
    stats: dict[tuple[str, str], list] = defaultdict(lambda: [0, 0, set(), set(), None])
    with connect() as conn:
        docs = conn.execute(
            """SELECT d.id, d.ticker, d.fiscal_period || '/' || d.fiscal_year FROM documents d
               WHERE d.owner_user_id IS NULL AND d.status IN ('verified', 'approved', 'needs_review')
               ORDER BY d.id""").fetchall()
        for doc_id, ticker, period in docs:
            try:
                record = _load_record(conn, doc_id)
            except RuntimeError:
                continue
            _, statements, _, template, _ = _check_cached(record)
            if template is None or (args.template and template != args.template):
                continue
            for c in validate(statements, template):
                if args.rule and not c.rule_id.startswith(args.rule):
                    continue
                s = stats[(template, c.rule_id)]
                s[0] += 1
                s[2].add(doc_id)
                s[4] = c.gate
                if c.passed:
                    s[1] += 1
                else:
                    s[3].add(doc_id)
                    if args.verbose:
                        print(f"  trượt {template} {c.rule_id} [{doc_id} {ticker} {period}] {c.column_kind}: "
                              f"vế trái {c.lhs:,.0f}, vế phải {c.rhs:,.0f}, lệch {c.lhs - c.rhs:,.0f}")
    print(f"{'mẫu':<6} {'ràng buộc':<24} {'bắt buộc':<8} {'BCTC':>5} {'ô kiểm':>7} {'khớp':>7}  BCTC trượt")
    for (template, rule_id), (n, ok, docs_seen, docs_bad, gate) in sorted(stats.items()):
        print(f"{template:<6} {rule_id:<24} {'có' if gate else 'chưa':<8} {len(docs_seen):>5} {n:>7} "
              f"{ok / n * 100:>6.1f}%  {len(docs_bad)}")


if __name__ == "__main__":
    main()
