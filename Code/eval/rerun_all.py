"""Chạy lại mọi phép đo dùng trong báo cáo kỹ thuật và in các con số chính ở một chỗ, không gọi mô hình.

    python eval/rerun_all.py --listed-before 2026-10-19 [--exclude-doc 5990] [--out ../Data/raw/rerun/<tên>]
                             [--skip sources,fault_injection] [--external --year 2026 --period Q3]

Chạy trong Docker (cần CSDL). Ghi vào thư mục --out (mặc định Data/raw/rerun/<phạm vi>_<giờ chạy>/):
  * summary.md: các con số theo đúng cách báo cáo gọi tên, kèm số báo cáo đang ghi (phạm vi 19/10/2026, 119 BCTC)
    để thấy ngay số nào đổi;
  * raw/<bước>.txt: nguyên văn đầu ra của từng lệnh đo.

Hai loại bước:
  * lệnh đo có sẵn trong eval/ (và `python -m services.extraction cost`), chạy thành tiến trình con với cờ chỉ chấm lại
    kết quả đã lưu. Tiến trình con chạy với khóa API để trống, nên kể cả khi một lệnh lỡ khởi tạo mô hình thì lần gọi
    cũng hỏng ngay chứ không tốn tiền; đầu ra có dòng chi phí gọi mô hình thì bước đó bị đánh dấu.
    born_digital chỉ chấm các BCTC đã có đủ kết quả đọc ở mọi mức ảnh; explanations chỉ chấm công văn đã có bản đọc
    lưu sẵn (công văn chưa đọc bị bỏ qua và liệt kê). external.py tải trang của nguồn ngoài nên chỉ chạy khi có --external.
  * phép đếm chạy ngay trong lệnh này (bảng phân loại ô và cách tách nhóm chưa kiểm được, so với người đọc thứ hai,
    BCTC cần người, chép lại cả báo cáo, chi phí mỗi BCTC, nguồn của số trên thẻ). Các phép đếm này nhận --exclude-doc
    để giữ đúng phạm vi cũ khi một BCTC trong phạm vi được đọc lại sau ngày chốt (TCX quý 4/2025, doc 5990, đọc lại
    20/10/2026: --listed-before 2026-10-19 nay ra 120 BCTC; thêm --exclude-doc 5990 ra lại 119 BCTC của báo cáo). Các lệnh
    đo chạy thành tiến trình con không có cờ này nên luôn tính theo --listed-before.

Tách nhóm "chưa kiểm được" (bảng phân loại ô của báo cáo, hai dòng 762 và 788 trên 119 BCTC): cùng là ô nhóm 6 và 8 của
eval/cell_funnel.py, chia theo tên dòng: lãi trên cổ phiếu, dòng "trong đó", mục ngoài bảng của ngân hàng là "dòng không
thuộc phép cộng nào của mẫu biểu"; mọi ô còn lại là "dòng có phép cộng nhưng hệ thống chưa khai báo".
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
NO_KEYS = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "LLM_API_KEY")
SPEND = re.compile(r"Chi phí gọi mô hình:|Tổng chi phí lần chạy này|Tổng [\d.]+ USD|Xong \d+ BCTC")

# Số báo cáo kỹ thuật đang ghi (phạm vi 119 BCTC, VN30, quý 4/2025 đến bán niên 2026, đã kiểm chứng hoặc duyệt tay tính
# đến 19/10/2026). Chỉ để so; khi báo cáo đổi số thì sửa ở đây.
REPORT = {
    "bctc": "119", "o": "35.196",
    "g1": "31.913", "g3": "1.491", "g2": "57", "g4": "152", "g7": "33", "uc_template": "762", "uc_undeclared": "788",
    "uc_total": "1.550", "g8": "1.244", "g6": "306", "pct_1_4": "95,5%", "pct_1_3": "95,1%", "pct_8": "3,5%",
    "pct_6": "0,9%", "pct_7": "0,1%", "pct_4": "152 (0,4%)", "est_ok": "99,5%", "est_low": "98,7%", "est_wrong6": "10",
    "eps_second": "264/279", "offbs_second": "342/368",
    "no_human": "97/119 (81,5%)", "approved": "4/119", "fixed_docs": "19/119", "fix_cells_avg": "8",
    "fix_entries": "158", "fix_flagged": "80 lượt / 8 BCTC", "fix_later": "78 lượt / 12 BCTC", "fix_emptied": "6",
    "fix_both": "2", "fix_cells_docs": "18",
    "card_total": "1.460", "card_cell_ok": "1.339", "card_image": "5", "card_computed": "116", "card_single": "0",
    "bd_goc": "3.105/3.107 (99,94%)", "bd_tot": "3.104/3.104 (100%)", "bd_vua": "3.102/3.102 (100%)",
    "bd_xau": "3.064/3.102 (98,8%)", "bd_xau_flagged": "27 ô / 3 BCTC", "bd_xau_slipped": "11", "bd_docs": "11",
    "cr_known": "154", "cr_both_missed": "5",
    "fi_docs": "114", "fi_digit": "2.000: 83,6% + 10,2% = 93,8%", "fi_sign": "500: 91,2% + 8,2% = 99,4%",
    "fi_drop": "500: 91,0% + 9,0% = 100%", "fi_swap": "500: 40,6% + 43,8% = 84,4%", "fi_loc_one": "32%",
    "fi_loc_wrong": "1/1.671", "fi_group": "6", "fi_rank": "68% / 42%",
    "sr_confirmed": "33.611", "sr_confirmed_agree": "97,7%", "sr_confirmed_unseen": "322", "sr_usd": "1,39",
    "sr_pages": "395/837",
    "rp_known": "165 ô / 25 BCTC", "rp_out": "75", "rp_in": "90", "rp_ok": "13 (14%)", "rp_group": "33 (37%)",
    "rp_miss": "44 (49%)", "rp_wrong": "5", "rp_groups": "42 nhóm, 191 ô", "rp_rank": "22/33",
    "rx_needed": "46", "rx_kept": "16 (35%)", "rx_kept_clean": "16/16", "rx_rot": "4", "rx_not": "30",
    "cost_q4_n": "29", "cost_q4_mean": "0,117", "cost_q4_median": "0,084", "cost_q4_p90": "0,173",
    "cost_q4_bank": "0,096", "cost_q4_corp": "0,136", "cost_rest": "90 BCTC: trung bình 0,108, trung vị 0,083",
    "cost_q4_steps": "định vị 1,2/23.917/770/0,021; chép 3,0/22.702/9.498/0,060; chép lại 2,7/10.110/5.658/0,033; "
                     "đọc lại ô 0,7/2.383/292/0,003; tổng 7,6/59.112/16.218/0,117",
    "src_both": "233: HOSE trước 161, Vietstock trước 62, dưới 15 phút 10",
    "src_median": "HOSE sớm hơn 0,6 giờ; 10% đầu 15,5 giờ; 90% Vietstock sớm hơn 7,1 giờ",
    "ext": "208/211",
}


def vn(x: float | int, digits: int = 0) -> str:
    """Số kiểu Việt Nam: 35.196; 99,5."""
    s = f"{x:,.{digits}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(a: float, b: float, digits: int = 1) -> str:
    return f"{vn(100 * a / b, digits)}%" if b else "?"


# ---------------------------------------------------------------- lệnh đo chạy thành tiến trình con

class Steps:
    def __init__(self, out: Path):
        self.raw = out / "raw"
        self.raw.mkdir(parents=True, exist_ok=True)
        self.log: list[tuple[str, str, float, int, str]] = []      # tên, lệnh, giây, mã thoát, ghi chú
        # PYTHONHASHSEED cố định: phép cấy lỗi duyệt tập hợp nên thứ tự (và kết quả, lệch tới 1 điểm %) đổi theo từng lần
        # chạy dù cùng --seed
        self.env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONHASHSEED="0", **{k: "" for k in NO_KEYS})

    def run(self, name: str, argv: list[str], timeout: int = 3600) -> str:
        t0 = time.time()
        cmd = [sys.executable, *argv]
        try:
            p = subprocess.run(cmd, cwd=CODE_DIR, env=self.env, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout)
            text, code = p.stdout + (f"\n--- stderr ---\n{p.stderr}" if p.stderr.strip() else ""), p.returncode
        except subprocess.TimeoutExpired as e:
            text, code = f"{e.stdout or ''}\nQUÁ GIỜ sau {timeout} giây", -1
        (self.raw / f"{name}.txt").write_text(" ".join(argv) + "\n\n" + text, encoding="utf-8")
        note = "CÓ DÒNG CHI PHÍ GỌI MÔ HÌNH, xem lại" if SPEND.search(text) else ""
        self.log.append((name, " ".join(argv), time.time() - t0, code, note))
        print(f"  {name}: {time.time() - t0:.0f} giây, mã thoát {code} {note}", flush=True)
        return text

    def skip(self, name: str, why: str) -> None:
        self.log.append((name, "", 0.0, 0, f"bỏ qua: {why}"))
        print(f"  {name}: bỏ qua ({why})", flush=True)


def _num(s: str) -> int:
    return int(s.replace(",", "").replace(".", ""))


def _find(pattern: str, text: str, default=None):
    m = re.search(pattern, text, re.M)
    return m.groups() if m else default


def _pymupdf_major() -> int:
    try:
        import pymupdf
        return int(str(pymupdf.__version__).split(".")[0])
    except Exception:
        return 0


def born_digital_sets() -> tuple[list[int], list[str], list[str]]:
    """BCTC trong kho và file ngoài kho có đủ kết quả đọc đã lưu ở mọi mức ảnh; các mục thiếu (sẽ phải gọi mô hình)."""
    from services.ingestion.registry import raw_data_dir
    root = raw_data_dir() / "born_digital"
    runs = {p.stem for p in (root / "runs").glob("*.json")}
    levels = ("tot", "vua", "xau")
    ids = sorted({int(s.split("_")[0]) for s in runs if s.split("_")[0].isdigit()})
    full_ids = [d for d in ids if all(f"{d}_{lv}" in runs for lv in levels)]
    missing = [f"doc {d}" for d in ids if d not in full_ids]
    names = []
    for e in json.loads((root / "set.json").read_text(encoding="utf-8")):
        if e.get("excluded"):
            continue
        name = f"{e['ticker']}_{e['period']}_{e['year']}"
        (names if all(f"{name}_{lv}" in runs for lv in ("goc", *levels)) else missing).append(name)
    return full_ids, names, missing


def cached_letters(conn) -> tuple[list[int], list[int]]:
    """Công văn giải trình mà eval/explanations.py sẽ chấm (cùng câu truy vấn), tách theo đã có bản đọc lưu sẵn hay chưa."""
    from services.ingestion.registry import raw_data_dir
    rows = conn.execute(
        """SELECT d.id FROM documents d
           JOIN LATERAL (SELECT storage_key FROM document_files WHERE document_id = d.id ORDER BY downloaded_at DESC
                         LIMIT 1) f ON true
           WHERE d.doc_type = 'explanation' AND d.duplicate_of IS NULL AND d.owner_user_id IS NULL
             AND d.fiscal_year >= 2025 AND d.ticker IN (SELECT ticker FROM companies WHERE tracked)""").fetchall()
    cache = raw_data_dir() / "explanations"
    have = [d for (d,) in rows if (cache / f"{d}.json").exists()]
    return have, [d for (d,) in rows if d not in have]


# ---------------------------------------------------------------- phép đếm chạy ngay trong lệnh này

def scope_docs(conn, listed_before: str | None, exclude: set[int], statuses=("verified", "approved", "needs_review")):
    rows = conn.execute(
        "SELECT id, ticker, fiscal_period || '/' || fiscal_year, status FROM documents WHERE owner_user_id IS NULL "
        "AND status = ANY(%s) AND (%s::date IS NULL OR source_listed_at < %s::date) ORDER BY id",
        (list(statuses), listed_before, listed_before)).fetchall()
    return [r for r in rows if r[0] not in exclude]


def _fold(s: str | None) -> str:
    from services.extraction.bank import fold
    return re.sub(r"\s+", " ", fold(s or "")).lower()


def unchecked_kind(label: str, st: str, row: int, offbs_from: int | None) -> str:
    """Loại dòng của một ô chưa kiểm được (nhóm 6, 8): ba loại đầu là dòng mẫu biểu không đặt vào phép cộng nào."""
    lab = _fold(label)
    if re.search(r"tren (mot )?co phieu|\beps\b", lab):
        return "lãi trên cổ phiếu"
    if re.match(r"^[-\s]*trong do", lab):
        return "dòng 'trong đó'"
    if st == "BS" and ((offbs_from is not None and row >= offbs_from)
                       or re.search(r"cam ket|bao lanh|no kho doi da xu ly|chua thu duoc|chung tu khac", lab)):
        return "ngoài bảng (ngân hàng)"
    return "có phép cộng chưa khai báo"


NOT_IN_TEMPLATE = ("lãi trên cổ phiếu", "dòng 'trong đó'", "ngoài bảng (ngân hàng)")


def cell_table(conn, docs) -> dict:
    from eval.cell_funnel import classify
    from services.extraction.pipeline import _load_record
    tally, kinds, kinds8, by_template = Counter(), Counter(), Counter(), Counter()
    per_doc: dict[int, Counter] = {}
    for d, *_ in docs:
        rec = _load_record(conn, d)
        offbs = next((i for i, r in enumerate(rec["raw"].get("BS", {}).get("rows", []))
                      if "ngoai bang" in _fold(r.get("label")) or "nghia vu no tiem an" in _fold(r.get("label"))), None)
        c = Counter()
        for cat, st, row, col, template, label in classify(conn, d):
            c[cat] += 1
            if cat in (6, 8):
                k = unchecked_kind(label, st, row, offbs)
                kinds[k] += 1
                kinds8[k] += cat == 8
                by_template[template] += 1
        per_doc[d] = c
        tally += c
    return {"tally": tally, "kinds": kinds, "kinds8": kinds8, "by_template": by_template, "per_doc": per_doc}


def second_read_table(conn, docs) -> dict:
    from eval.second_read import compare_document
    from services.extraction.pipeline import _load_record
    by_cat: dict[int, Counter] = defaultdict(Counter)
    n_docs = gate_ok = 0
    usd = 0.0
    for d, _, period, _ in docs:
        rows = compare_document(conn, d, period.split("/")[0])
        if not rows:
            continue
        n_docs += 1
        gate_ok += rows[0]["second_gate_ok"]
        usd += _load_record(conn, d)["second_read"].get("usd") or 0
        for r in rows:
            by_cat[r["cat"]][r["result"]] += 1
    return {"docs": n_docs, "gate_ok": gate_ok, "usd": usd, "by_cat": by_cat}


def unchecked_pages(conn, docs) -> tuple[int, int]:
    """(trang của các báo cáo còn ô chưa có phép kiểm, tổng trang báo cáo), tính như khi chưa có lần đọc thứ hai."""
    from services.extraction.evidence import document_evidence
    from services.extraction.pipeline import _load_record
    from services.extraction.second_read import statement_pages
    total = need = 0
    for d, *_ in docs:
        rec = {k: v for k, v in _load_record(conn, d).items() if k != "second_read"}
        ev = document_evidence(conn, d, load=lambda x, d=d, rec=rec: rec if x == d else _load_record(conn, x))
        if ev is None:
            continue
        sp = statement_pages(rec)
        total += sum(len(v) for v in sp.values())
        sts = {st for (st, _, _), s in ev.status.items() if s["status"] == "none"}
        need += sum(len(sp.get(st, [])) for st in sts)
    return need, total


def human_work(conn, docs) -> dict:
    """BCTC cần người (duyệt tay, sửa ô, sửa mã) và các lượt sửa tay, tách theo nguồn phát hiện."""
    from services.extraction.pipeline import _load_record
    t = Counter()
    flagged_docs, later_docs, fixed_docs, cells_docs = set(), set(), set(), set()
    later_note_docs = set()
    for d, *_ in docs:
        rec = _load_record(conn, d)
        fixes = [m for m in rec.get("manual_fixes", []) if re.search(r"\d", f"{m.get('before') or ''}{m.get('after') or ''}")]
        codes = rec.get("manual_code_fixes", [])
        approved = bool(rec.get("approval"))
        t["BCTC"] += 1
        t["không cần người"] += not (fixes or codes or approved)
        t["duyệt tay"] += approved
        t["sửa ít nhất một ô hoặc mã"] += bool(fixes or codes)
        t["duyệt tay và sửa"] += approved and bool(fixes or codes)
        t["lượt sửa số"] += len(fixes)
        t["lượt sửa mã"] += len(codes)
        if fixes or codes:
            fixed_docs.add(d)
        if fixes:
            cells_docs.add(d)
        last = {}
        for m in fixes:
            last[(m["statement"], m["row"], m["column_kind"])] = m
        for m in last.values():
            # Đếm theo ô (lượt sửa cuối của mỗi ô), như báo cáo. Người đọc thứ hai chạy trên toàn bộ phạm vi ngày
            # 18/10/2026; ô sửa từ ngày đó là do nó chỉ ra
            later = bool(re.search(r"\b(1[89]|2\d|3[01])/10/2026|/1[12]/2026", m.get("by") or ""))
            t["lượt sửa: hệ thống tự báo (trước 18/10)" if not later else "lượt sửa: người đọc thứ hai chỉ ra (từ 18/10)"] += 1
            (later_docs if later else flagged_docs).add(d)
            if "người đọc thứ hai" in (m.get("note") or ""):
                t["lượt sửa ghi chú 'người đọc thứ hai'"] += 1
                later_note_docs.add(d)
        t["ô khác nhau đã sửa"] += len(last)
        t["ô sửa xong để trống"] += sum(1 for (st, row, col) in last
                                         if not re.search(r"\d", str(rec["raw"][st]["rows"][row]["values"].get(col) or "")))
    t["BCTC có lượt sửa hệ thống tự báo"] = len(flagged_docs)
    t["BCTC có lượt sửa người đọc thứ hai chỉ ra"] = len(later_docs)
    t["BCTC thuộc cả hai nhóm"] = len(flagged_docs & later_docs)
    t["BCTC có ghi chú 'người đọc thứ hai'"] = len(later_note_docs)
    t["BCTC có sửa số"] = len(cells_docs)
    return dict(t)


def reextracts(conn, docs) -> dict:
    from services.extraction.pipeline import _check, _load_record
    t = Counter()
    for d, *_ in docs:
        rec = _load_record(conn, d)
        logs = rec.get("reextracts") or []
        if not logs:
            continue
        checks = _check(rec)[4]
        for st in sorted({x["statement"] for x in logs}):
            ls = [x for x in logs if x["statement"] == st]
            kept = any(x["kept"] for x in ls)
            t["phải chép lại"] += 1
            t["giữ bản chép lại"] += kept
            t["không tốt hơn, giữ bản cũ"] += not kept
            t["giữ nhờ xoay 180 độ"] += any(x.get("rotation_added") and x["kept"] for x in ls)
            clean = not [c for c in checks if c.gate and not c.passed and c.rule_id.split("_")[0] == st]
            t["giữ và nay đạt mọi ràng buộc bắt buộc của báo cáo"] += kept and clean
    return dict(t)


def _step_group(step: str) -> str:
    if step.startswith(("locate", "page_classification", "orientation")):
        return "định vị trang"
    if step.startswith(("statement", "extend", "empty_page")):
        return "chép BCĐKT, KQKD, LCTT"
    if step.startswith("reextract"):
        return "chép lại trang còn lệch"
    if any(k in step for k in ("reread", "verify", "repair")):
        return "đọc lại ô"
    if step.startswith("second_read"):
        return "đọc lần hai"
    return step


def costs(conn, docs) -> dict:
    """Chi phí đọc một BCTC (như bảng chi phí của báo cáo): giá theo mô hình của bản ghi, theo kỳ và theo bước."""
    from services.costs import _records
    from services.llm import cost_usd
    meta = {d: (period, tpl) for d, period, tpl in conn.execute(
        "SELECT d.id, d.fiscal_period || '/' || d.fiscal_year, c.template FROM documents d JOIN companies c USING (ticker)")}
    scope = {d for d, *_ in docs}
    per_doc, steps = {}, defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0.0]))
    for r in _records():
        d = r.get("document_id")
        u, m = r.get("usage") or {}, r.get("model")
        if d not in scope or not u.get("calls"):
            continue
        per_doc[d] = (cost_usd(m, u.get("input_tokens", 0), u.get("output_tokens", 0)) or 0.0, u.get("usd"))
        for s, su in (r.get("usage_by_step") or {}).items():
            x = steps[meta[d][0]][_step_group(s)]
            x[0] += su.get("calls", 0)
            x[1] += su.get("input_tokens", 0)
            x[2] += su.get("output_tokens", 0)
            x[3] += cost_usd(m, su.get("input_tokens", 0), su.get("output_tokens", 0)) or 0.0

    def stats(ds):
        v = sorted(per_doc[d][0] for d in ds)
        if not v:
            return None
        return {"n": len(v), "mean": statistics.mean(v), "median": statistics.median(v), "p90": v[int(0.9 * (len(v) - 1))]}

    by_period = defaultdict(list)
    for d in per_doc:
        by_period[meta[d][0]].append(d)
    out = {"no_record": sorted(scope - set(per_doc)), "periods": {}}
    for p, ds in sorted(by_period.items()):
        n = len(ds)
        out["periods"][p] = dict(stats(ds), by_template={tpl: stats([d for d in ds if meta[d][1] == tpl])
                                                       for tpl in ("bank", "corporate", "securities")},
                                 steps={g: [x[0] / n, x[1] / n, x[2] / n, x[3] / n] for g, x in steps[p].items()})
    out["all"] = stats(list(per_doc))
    q4 = [p for p in by_period if p.startswith("Q4/2025")]
    out["rest"] = stats([d for p, ds in by_period.items() if p not in q4 for d in ds])
    logged = [v for _, v in per_doc.values() if v is not None]
    out["usd_logged_mean"] = statistics.mean(logged) if logged else None
    return out


def card_sources(conn, docs) -> dict:
    """Số trên thẻ KQKD theo nguồn: lấy thẳng từ một ô (theo trạng thái bằng chứng của ô đó) hay code cộng từ nhiều ô."""
    from services.extraction.evidence import document_evidence
    from services.metrics.service import card_for
    t = Counter()
    for d, _, _, status in docs:
        if status not in ("verified", "approved"):
            continue
        got = card_for(conn, d)
        if not got:
            continue
        card, _ = got
        ev = document_evidence(conn, d)
        for m in card.metrics:
            for col in ("q_cur", "q_prev_year", "ytd_cur", "ytd_prev_year"):
                v = getattr(m, col, None)
                if v is None or v.value is None:
                    continue
                if v.source is None:
                    t["tính từ nhiều ô"] += 1
                    continue
                s = ev.status.get((v.source.statement, v.source.code, v.source.column), {}).get("status", "không thấy") \
                    if ev else "không có bằng chứng"
                t[s] += 1
    return dict(t)


# ---------------------------------------------------------------- tóm tắt

class Summary:
    def __init__(self):
        self.lines: list[str] = []
        self.rows: list[tuple[str, str, str, str]] = []      # khóa, nhãn, đo lại, báo cáo đang ghi

    def h(self, title: str) -> None:
        self.lines += ["", f"## {title}", ""]

    def p(self, text: str) -> None:
        self.lines.append(text)

    def n(self, key: str | None, label: str, value) -> None:
        value = "?" if value is None else str(value)
        self.lines.append(f"- {label}: **{value}**" + (f" (báo cáo đang ghi: {REPORT[key]})" if key in REPORT else ""))
        if key:
            self.rows.append((key, label, value, REPORT.get(key, "")))

    def table(self, header: list[str], rows: list[list]) -> None:
        self.lines += ["", "| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
        self.lines += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
        self.lines.append("")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--listed-before", help="phạm vi: BCTC Vietstock đăng trước ngày này (YYYY-MM-DD); báo cáo hiện dùng "
                                            "2026-10-19; bỏ trống là mọi BCTC")
    ap.add_argument("--exclude-doc", type=int, nargs="*", default=[],
                    help="bỏ các BCTC này khỏi các phép đếm chạy trong lệnh này (5990: giữ đúng 119 BCTC cũ)")
    ap.add_argument("--out", help="thư mục ghi kết quả (mặc định Data/raw/rerun/<phạm vi>_<giờ chạy>)")
    ap.add_argument("--skip", default="", help="các bước bỏ qua, cách nhau dấu phẩy (ví dụ sources,fault_injection,cards)")
    ap.add_argument("--external", action="store_true", help="chạy cả eval/external.py (tải trang của nguồn ngoài)")
    ap.add_argument("--year", type=int, help="cho --external: năm của quý mới nhất")
    ap.add_argument("--period", choices=("Q1", "Q2", "Q3", "Q4"), help="cho --external: quý mới nhất")
    ap.add_argument("--born-digital-files", metavar="FILE",
                    help="đầu ra của `eval/born_digital.py files` chạy trong venv (không cần CSDL) để dùng thay cho lần chạy "
                         "trong Docker: đáp án của file ngoài kho dựng từ lớp chữ, và bản pymupdf trong ảnh Docker (2.x) "
                         "tách chữ khác bản trong venv (1.28) nên chấm lệch")
    ap.add_argument("--err-rate-unchecked", type=float, default=0.03,
                    help="tỷ lệ sai giả định của ô chỉ có một lần đọc, để ước tính 'đúng mà không cần người sửa' (báo cáo: "
                         "khoảng 3%%, tỷ lệ người đọc thứ hai tìm ra lỗi ở nhóm chưa có phép kiểm)")
    args = ap.parse_args()
    if args.external and not (args.year and args.period):
        ap.error("--external cần --year và --period")
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    from services.db import connect
    from services.ingestion.registry import raw_data_dir

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = Path(args.out) if args.out else raw_data_dir() / "rerun" / f"{args.listed_before or 'tatca'}_{stamp}"
    out.mkdir(parents=True, exist_ok=True)
    steps = Steps(out)
    lb = ["--listed-before", args.listed_before] if args.listed_before else []
    exclude = set(args.exclude_doc)
    S = Summary()
    t_start = time.time()

    with connect() as conn:
        docs = scope_docs(conn, args.listed_before, exclude)
        failed = scope_docs(conn, args.listed_before, exclude, statuses=("failed",))
        bd_ids, bd_names, bd_missing = born_digital_sets()
        letters, letters_missing = cached_letters(conn)

    # 1. Lệnh đo có sẵn
    print("Lệnh đo:", flush=True)
    raw = {}
    plan = [
        ("cell_funnel", ["eval/cell_funnel.py", *lb]),
        ("capture_recapture", ["eval/capture_recapture.py", *lb]),
        ("second_read_compare", ["eval/second_read.py", "compare", *lb]),
        ("repair", ["eval/repair.py", *lb]),
        ("fault_injection", ["eval/fault_injection.py", *lb]),
        ("born_digital_measure", ["eval/born_digital.py", "measure", "--doc-id", *map(str, bd_ids)] if bd_ids else None),
        ("born_digital_degraded", ["eval/born_digital.py", "degraded", "--doc-id", *map(str, bd_ids)] if bd_ids else None),
        ("born_digital_files", ["eval/born_digital.py", "files", "--only", *bd_names] if bd_names else None),
        ("explanations", ["eval/explanations.py", "--doc-id", *map(str, letters)] if letters else None),
        ("latency", ["eval/latency.py"]),
        ("sources", ["eval/sources.py"]),
        ("cost", ["-m", "services.extraction", "cost"]),
        ("external", ["eval/external.py", "--year", str(args.year), "--period", args.period] if args.external else None),
    ]
    pymupdf_major = _pymupdf_major()
    for name, argv in plan:
        if name == "born_digital_files" and args.born_digital_files:
            raw[name] = Path(args.born_digital_files).read_text(encoding="utf-8")
            (steps.raw / f"{name}.txt").write_text(raw[name], encoding="utf-8")
            steps.log.append((name, f"đọc từ {args.born_digital_files}", 0.0, 0, "đầu ra chạy trong venv"))
            continue
        if name in skip:
            steps.skip(name, "theo --skip")
        elif argv is None:
            steps.skip(name, "chỉ chạy khi có --external (tải trang nguồn ngoài)" if name == "external"
                       else "không có kết quả đã lưu để chấm lại")
        else:
            raw[name] = steps.run(name, argv)

    # 2. Phép đếm trong lệnh này
    print("Phép đếm:", flush=True)
    with connect() as conn:
        t0 = time.time()
        ct = cell_table(conn, docs)
        sr = second_read_table(conn, docs) if "second_read_compare" not in skip else None
        pages = unchecked_pages(conn, docs) if "pages" not in skip else None
        hw = human_work(conn, docs)
        rx = reextracts(conn, docs)
        cs = costs(conn, docs)
        try:
            cards = card_sources(conn, docs) if "cards" not in skip else None
        except Exception as e:          # mã tính thẻ đang được sửa song song: không để cả lệnh hỏng
            cards = {"lỗi": repr(e)}
        print(f"  xong sau {time.time() - t0:.0f} giây", flush=True)

    # ---------------------------------------------------------------- viết tóm tắt
    tally = ct["tally"]
    n_cells = sum(tally.values())
    n_docs = len(docs)
    S.p("# Chạy lại các phép đo của báo cáo kỹ thuật")
    S.p("")
    S.p(f"Chạy lúc {datetime.now():%H:%M %d/%m/%Y}; phạm vi: BCTC Vietstock đăng trước {args.listed_before or '(không giới hạn)'}"
        f", trạng thái đã kiểm chứng, duyệt tay hoặc chờ duyệt"
        + (f"; bỏ ra khỏi phép đếm trong lệnh: doc {', '.join(map(str, sorted(exclude)))}" if exclude else "") + ".")
    S.p("Số kiểu 'báo cáo đang ghi' là số trong báo cáo kỹ thuật tại phạm vi 19/10/2026 (119 BCTC), chỉ để so.")
    if exclude:
        S.p("Lưu ý: các lệnh đo chạy thành tiến trình con (mục 3 trở đi) không bỏ được BCTC nào, nên chúng tính theo "
            "đúng --listed-before (có cả các BCTC ở --exclude-doc).")

    S.h("1. Phạm vi")
    by_status = Counter(s for *_, s in docs)
    S.n("bctc", "Số BCTC trong phạm vi (đã kiểm chứng/duyệt tay/chờ duyệt)", vn(n_docs))
    S.p(f"- Theo trạng thái: {dict(by_status)}; BCTC lỗi cùng phạm vi: {len(failed)}"
        + (f" ({', '.join(f'{t} {p} doc {d}' for d, t, p, _ in failed)})" if failed else ""))
    per = defaultdict(Counter)
    for d, t, p, s in docs + failed:
        per[p][s] += 1
    S.table(["Kỳ", "Đã kiểm chứng", "Đã duyệt tay", "Chờ duyệt", "Lỗi"],
            [[p, c["verified"], c["approved"], c["needs_review"], c["failed"]]
             for p, c in sorted(per.items(), key=lambda x: (x[0].split("/")[1], x[0]))])
    S.n("o", "Tổng ô số", vn(n_cells))

    S.h("2. Bảng phân loại ô (tab:theoo) và kết quả chính theo ô (tab:ketquachinh)")
    for key, cat, label in (("g1", 1, "Đúng ngay lần đọc đầu, có phép kiểm xác nhận"),
                            ("g3", 3, "Thuộc báo cáo phải chép lại trang, sau đó có phép kiểm xác nhận"),
                            ("g2", 2, "Đọc lại riêng ô rồi mới khớp"),
                            ("g4", 4, "Người duyệt sửa sau khi đối chiếu ảnh gốc"),
                            ("g7", 7, "Phép kiểm vẫn lệch, người duyệt đã đối chiếu ảnh: chính BCTC in lệch")):
        S.n(key, label, f"{vn(tally[cat])} ({pct(tally[cat], n_cells)})")
    kinds, kinds8 = ct["kinds"], ct["kinds8"]
    a = sum(kinds[k] for k in NOT_IN_TEMPLATE)
    b = kinds["có phép cộng chưa khai báo"]
    S.n("uc_template", "Chưa kiểm được: dòng không thuộc phép cộng nào của mẫu biểu",
        f"{vn(a)} ({pct(a, n_cells)}): lãi trên cổ phiếu {kinds['lãi trên cổ phiếu']}, ngoài bảng ngân hàng "
        f"{kinds['ngoài bảng (ngân hàng)']}, dòng 'trong đó' {kinds[NOT_IN_TEMPLATE[1]]}")
    S.n("uc_undeclared", "Chưa kiểm được: dòng có phép cộng nhưng hệ thống chưa khai báo", f"{vn(b)} ({pct(b, n_cells)})")
    S.n("uc_total", "Chưa kiểm được, tổng (nhóm 6 + 8)", vn(tally[6] + tally[8]))
    S.p(f"- Chưa kiểm được theo mẫu: {dict(ct['by_template'])}; nhóm 5 (cần xem ảnh, chưa xử lý): {tally[5]}; "
        f"nhóm 9 (hai lần đọc khác, người xác nhận lần đầu đúng): {tally[9]}")
    S.n("g8", "Chưa có phép kiểm, hai lần đọc trùng nhau (nhóm 8)", vn(tally[8]))
    S.n("g6", "Chỉ có một lần đọc (nhóm 6)", vn(tally[6]))
    S.n("eps_second", "Lãi trên cổ phiếu: hai lần đọc trùng / tổng", f"{kinds8['lãi trên cổ phiếu']}/{kinds['lãi trên cổ phiếu']}")
    S.n("offbs_second", "Ngoài bảng ngân hàng: hai lần đọc trùng / tổng",
        f"{kinds8['ngoài bảng (ngân hàng)']}/{kinds['ngoài bảng (ngân hàng)']}")
    c14 = tally[1] + tally[2] + tally[3] + tally[4]
    c13 = c14 - tally[4]
    S.n("pct_1_4", "Ô được phép kiểm xác nhận (nhóm 1-4)", pct(c14, n_cells))
    S.n("pct_1_3", "... không tính ô người sửa: có phép kiểm tự động xác nhận (nhóm 1-3)", pct(c13, n_cells))
    S.n("pct_8", "Chưa có phép kiểm, hai lần đọc độc lập trùng nhau", pct(tally[8] + tally[9], n_cells))
    S.n("pct_6", "Chỉ có một lần đọc, chưa có bằng chứng", f"{pct(tally[6], n_cells)} ({tally[6]} ô)")
    S.n("pct_7", "Đọc đúng nhưng chính BCTC in lệch, người xem ảnh xác nhận", pct(tally[7], n_cells))
    S.n("pct_4", "Ô người phải sửa sau khi xem ảnh", f"{tally[4]} ({pct(tally[4], n_cells)})")
    wrong6 = args.err_rate_unchecked * tally[6]
    ok = c13 + tally[8] + tally[9] + tally[7] + tally[6] - wrong6
    S.n("est_wrong6", f"Ô sai ước tính trong nhóm một lần đọc (giả định {vn(100 * args.err_rate_unchecked)}%)", vn(wrong6, 1))
    S.n("est_ok", "Ô đúng mà không cần người sửa (ước tính)", f"{pct(ok, n_cells)} ({pct(ok, n_cells, 2)})")
    S.n("est_low", "Cận dưới (coi mọi ô một lần đọc là sai)", pct(c13 + tally[8] + tally[9] + tally[7], n_cells))
    S.p("- Cách tính ước tính: (nhóm 1-3 + 7 + 8 + 9 + nhóm 6 trừ số ô sai giả định) / tổng ô; tỷ lệ sai giả định của "
        "nhóm 6 là tham số (--err-rate-unchecked), không do lệnh nào đo.")
    if exclude and len(exclude) <= 5:
        for d in sorted(exclude):
            with connect() as conn:
                extra = cell_table(conn, [(d, "", "", "")])["tally"]
            S.p(f"- doc {d} (bị bỏ khỏi phạm vi) có {vn(sum(extra.values()))} ô: "
                + ", ".join(f"nhóm {k} {v}" for k, v in sorted(extra.items())))

    S.h("3. BCTC cần người (tab:ketquachinh) và lượt sửa tay")
    nb = hw["BCTC"]
    S.n("no_human", "BCTC không cần người làm gì", f"{hw['không cần người']}/{nb} ({pct(hw['không cần người'], nb)})")
    S.n("approved", "BCTC người chỉ xem ảnh rồi duyệt", f"{hw['duyệt tay']}/{nb}")
    S.n("fixed_docs", "BCTC người phải sửa ít nhất một ô (kể cả chỉ sửa mã)", f"{hw['sửa ít nhất một ô hoặc mã']}/{nb}")
    S.p(f"- BCTC vừa duyệt tay vừa có sửa: {hw['duyệt tay và sửa']} (vì vậy ba dòng trên cộng ra "
        f"{hw['không cần người'] + hw['duyệt tay'] + hw['sửa ít nhất một ô hoặc mã']}, không phải {nb})")
    S.n("fix_cells_docs", "BCTC có sửa số (không tính BCTC chỉ sửa mã)", hw["BCTC có sửa số"])
    S.n("fix_cells_avg", "Ô sửa trung bình mỗi BCTC phải sửa",
        vn(tally[4] / hw["sửa ít nhất một ô hoặc mã"]) if hw["sửa ít nhất một ô hoặc mã"] else "?")
    S.n("fix_entries", "Lượt sửa (theo ô có sửa số, kể cả ô sửa xong để trống)", hw["ô khác nhau đã sửa"])
    S.p(f"- Mọi lượt sửa số đã ghi, kể cả sửa lại cùng ô: {hw['lượt sửa số']}")
    S.n("fix_flagged", "Lượt sửa do hệ thống tự báo (sửa trước 18/10/2026)",
        f"{hw['lượt sửa: hệ thống tự báo (trước 18/10)']} lượt / {hw['BCTC có lượt sửa hệ thống tự báo']} BCTC")
    S.n("fix_later", "Lượt sửa do người đọc thứ hai chỉ ra (sửa từ 18/10/2026)",
        f"{hw['lượt sửa: người đọc thứ hai chỉ ra (từ 18/10)']} lượt / {hw['BCTC có lượt sửa người đọc thứ hai chỉ ra']} BCTC")
    S.n("fix_both", "BCTC thuộc cả hai nhóm", hw["BCTC thuộc cả hai nhóm"])
    noted, noted_docs = hw.get("lượt sửa ghi chú 'người đọc thứ hai'", 0), hw["BCTC có ghi chú 'người đọc thứ hai'"]
    S.p(f"- Ô sửa có ghi chú 'người đọc thứ hai': {noted} ở {noted_docs} BCTC; lượt sửa mã: {hw['lượt sửa mã']}")
    S.n("fix_emptied", "Ô sửa xong để trống (xóa số chép nhầm)", hw["ô sửa xong để trống"])
    S.p("- Nguồn phát hiện được tách theo ngày sửa: người đọc thứ hai chạy trên toàn bộ phạm vi ngày 18/10/2026. Từ mùa "
        "quý 3 cách tách này không còn đúng (lần đọc thứ hai chạy tự động), cần đếm theo ô 'cần xem ảnh'.")

    if cards is not None:
        S.h("4. Số trên thẻ KQKD theo nguồn")
        if "lỗi" in cards:
            S.p(f"- Không tính được: {cards['lỗi']}")
        else:
            total = sum(cards.values())
            cell_ok = sum(v for k, v in cards.items() if k in ("sum", "period", "both", "differs", "restated"))
            S.n("card_total", "Số trên thẻ", vn(total))
            S.n("card_cell_ok", "Lấy thẳng từ một ô có phép kiểm hoặc đã đọc lại xác nhận", vn(cell_ok))
            S.n("card_image", "Chỗ chính BCTC in lệch, người duyệt đã xem ảnh", cards.get("image_ok", 0) + cards.get("conflict", 0))
            S.n("card_computed", "Code cộng từ nhiều ô", cards.get("tính từ nhiều ô", 0))
            S.n("card_single", "Lấy thẳng từ một ô chỉ có một lần đọc hoặc hai lần đọc khác nhau",
                sum(cards.get(k, 0) for k in ("none", "second", "second_differs", "không thấy")))
            S.p(f"- Chi tiết theo trạng thái ô: {cards}")

    S.h("5. Đo bằng đáp án có sẵn (tab:dapan)")
    S.p(f"- BCTC trong kho: {bd_ids}; file ngoài kho: {bd_names}"
        + (f"; bỏ qua vì chưa có đủ kết quả đọc (sẽ phải gọi mô hình): {bd_missing}" if bd_missing else ""))
    bd = defaultdict(lambda: [0, 0, 0, 0, 0])        # đúng, tổng, BCTC bị báo, ô sai trong BCTC bị báo, ô lọt
    if "born_digital_measure" in raw:
        g = _find(r"^tự động: (\d+)/(\d+) ô đúng", raw["born_digital_measure"])
        if g:
            bd["goc"][0] += int(g[0])
            bd["goc"][1] += int(g[1])
    names = {"bản gốc": "goc", "scan tốt": "tot", "scan trung bình": "vua", "scan xấu": "xau"}
    for step in ("born_digital_degraded", "born_digital_files"):
        for m in re.finditer(r"^(bản gốc|scan tốt|scan trung bình|scan xấu): (\d+)/(\d+) ô đúng .*?; (\d+) BCTC bị báo, "
                             r"chứa (\d+) ô sai; (\d+) ô sai lọt qua", raw.get(step, ""), re.M):
            x = bd[names[m.group(1)]]
            for i, v in enumerate(m.groups()[1:]):
                x[i] += int(v)
    S.n("bd_docs", "Số BCTC có đáp án", len(bd_ids) + len(bd_names))
    for key, lv, label in (("bd_goc", "goc", "Ảnh gốc của file"), ("bd_tot", "tot", "Giống bản scan tốt (200 dpi)"),
                           ("bd_vua", "vua", "Giống bản scan trung bình (120 dpi)"),
                           ("bd_xau", "xau", "Giống bản scan xấu (72 dpi)")):
        x = bd[lv]
        S.n(key, label, f"{vn(x[0])}/{vn(x[1])} ({pct(x[0], x[1], 2)})" if x[1] else None)
    x = bd["xau"]
    S.n("bd_xau_flagged", "72 dpi: ô sai nằm trong BCTC hệ thống đã báo", f"{x[3]} ô / {x[2]} BCTC")
    S.n("bd_xau_slipped", "72 dpi: ô sai lọt qua", x[4])
    if pymupdf_major >= 2 and not args.born_digital_files:
        S.p("- **Cảnh báo:** phần file ngoài kho chấm bằng pymupdf bản mới trong Docker, tách lớp chữ khác bản venv nên "
            "đáp án dựng lại lệch (đo 22/10/2026: 1.287/1.299 thay vì 1.309/1.309 ở ảnh gốc). Chạy trong venv "
            "`RAW_DATA_DIR=../Data/raw .venv/Scripts/python eval/born_digital.py files --only "
            f"{' '.join(bd_names)} > ../Data/raw/rerun/bd_files.txt` rồi chạy lại lệnh này với "
            "`--born-digital-files /app/Data/raw/rerun/bd_files.txt`.")
    S.p("- Ảnh gốc của BCTC trong kho tính theo số hệ thống tự đọc (trước khi người sửa); file ngoài kho tính theo lần "
        "đọc 'bản gốc' đã lưu. Số BCTC bị báo ở ảnh gốc không cộng ở đây.")

    S.h("6. Phép kiểm bắt được bao nhiêu lỗi (tab:caloi) và bước định vị trên lỗi cấy")
    fi = raw.get("fault_injection", "")
    g = _find(r"của (\d+) BCTC đã kiểm chứng", fi)
    S.n("fi_docs", "BCTC được cấy lỗi", g[0] if g else None)
    for key, kind in (("fi_digit", "nhầm một chữ số"), ("fi_sign", "mất dấu âm"), ("fi_drop", "thiếu một chữ số"),
                      ("fi_swap", "đổi chỗ hai dòng cùng một phép cộng")):
        g = _find(rf"^  {kind}: (\d+) lỗi; ràng buộc bắt buộc trong BCTC bắt (\d+) .*?thêm công thức không bắt buộc "
                  rf"(\d+), đối chiếu kỳ khác (\d+) .*?lọt (\d+)", fi)
        if g:
            n, gate, soft, cross, miss = map(int, g)
            S.n(key, kind.capitalize(), f"{vn(n)}: {pct(gate, n)} + {pct(soft + cross, n)} = {pct(n - miss, n)}")
        else:
            S.n(key, kind.capitalize(), None)
    g = _find(r"^Định vị (\d+) lỗi", fi)
    n_loc = int(g[0]) if g else 0
    one = _find(r"chỉ đúng một ô, đúng số: (\d+)", fi)
    wrong = _find(r"đề xuất sai ô hoặc sai số: (\d+)", fi, ("0",))
    S.n("fi_loc_one", "Định vị chỉ đúng một ô và đúng số", pct(int(one[0]), n_loc, 0) if one and n_loc else None)
    S.n("fi_loc_wrong", "Đề xuất nhầm ô", f"{wrong[0]}/{vn(n_loc)}" if n_loc else None)
    g = _find(r"cỡ trung bình ([\d.]+); ô đúng đứng đầu: theo mô hình nhầm (\d+)%, theo số chữ số khác (\d+)%", fi)
    S.n("fi_group", "Cỡ nhóm ngang điểm trung bình", vn(float(g[0]), 1) if g else None)
    S.n("fi_rank", "Ô đúng đứng đầu nhóm: theo tần suất nhầm / theo số chữ số khác", f"{g[1]}% / {g[2]}%" if g else None)

    S.h("7. Người đọc thứ hai (sec:nguoidoc2)")
    if sr:
        bc = sr["by_cat"]
        conf = sum((bc[c] for c in (1, 2, 3, 4)), Counter())
        nconf = sum(conf.values())
        S.p(f"- BCTC có lần đọc thứ hai: {sr['docs']}; người đọc thứ hai tự đạt mọi phép kiểm bắt buộc ở "
            f"{sr['gate_ok']}/{sr['docs']}")
        S.n("sr_usd", "Chi phí lần đọc thứ hai (USD)", vn(sr["usd"], 2))
        S.n("sr_confirmed", "Nhóm đã được phép kiểm xác nhận: số ô so được", vn(nconf))
        S.n("sr_confirmed_agree", "... hai lần đọc trùng", pct(conf["trùng"], nconf))
        S.n("sr_confirmed_unseen", "... người thứ hai không chép", conf["không thấy"])
        S.p(f"- ... khác chữ số {conf['khác']}, khác đơn vị {conf['khác đơn vị']}")
        for c in sorted(bc):
            t = bc[c]
            S.p(f"- nhóm {c}: {vn(sum(t.values()))} ô; trùng {vn(t['trùng'])}, khác {t['khác']}, khác đơn vị "
                f"{t['khác đơn vị']}, không thấy {t['không thấy']}")
        S.p("- Số ô so được ít hơn số ô của nhóm vì bỏ các dòng không xác định được khóa.")
    if pages:
        S.n("sr_pages", "Trang báo cáo còn ô chưa có phép kiểm / tổng trang báo cáo", f"{pages[0]}/{pages[1]}")

    S.h("8. Ước lượng số lỗi còn sót bằng hai lưới (bắt-thả-bắt lại)")
    g = _find(r"^(\d+) ô đã biết là đọc sai; phép kiểm \(A\) bắt (\d+), người đọc thứ hai \(B\) bắt (\d+), cả hai (\d+), "
              r"không bên nào (\d+)", raw.get("capture_recapture", ""))
    S.n("cr_known", "Ô đã biết là đọc sai (có lần đọc thứ hai)", g[0] if g else None)
    S.n("cr_both_missed", "Cả phép kiểm và người đọc thứ hai cùng bỏ sót", g[4] if g else None)
    if g:
        S.p(f"- Phép kiểm bắt {g[1]}, người đọc thứ hai bắt {g[2]}, cả hai {g[3]}")
    g = _find(r"^Chapman: (.*)$", raw.get("capture_recapture", ""))
    if g:
        S.p(f"- Chapman: {g[0]}")

    S.h("9. Định vị ô đọc sai trên lỗi thật (fig:evalrepair)")
    rp = raw.get("repair", "")
    g = _find(r"^(\d+) tài liệu, (\d+) ô đã biết là đọc sai", rp)
    S.n("rp_known", "Bộ đề", f"{g[1]} ô / {g[0]} BCTC" if g else None)
    for key, pat, label in (("rp_out", r"ngoài tầm \(.*?\): (\d+)", "Ngoài tầm"), ("rp_in", r"trong tầm: (\d+)", "Trong tầm")):
        g = _find(pat, rp)
        S.n(key, label, g[0] if g else None)
    for key, word in (("rp_ok", "đúng"), ("rp_group", "cần đọc lại"), ("rp_miss", "sót")):
        g = _find(rf"^  {word}\s+(\d+)\s+\((\d+)%\)", rp)
        S.n(key, word.capitalize(), f"{g[0]} ({g[1]}%)" if g else None)
    g = _find(r"đề xuất sai\s+(\d+)", rp)
    S.n("rp_wrong", "Đề xuất sai", g[0] if g else None)
    g = _find(r"nhóm phương án ngang nhau: (\d+), tổng (\d+) ô", rp)
    S.n("rp_groups", "Nhóm cần đọc lại", f"{g[0]} nhóm, {g[1]} ô" if g else None)
    g = _find(r"trong (\d+) ô cần đọc lại, xếp theo mô hình nhầm .*? lên đầu (\d+) lần", rp)
    S.n("rp_rank", "Lỗi thật: ô đúng đứng đầu nhóm khi xếp theo tần suất nhầm", f"{g[1]}/{g[0]}" if g else None)
    S.p("- Tỷ lệ 'nếu bỏ BCTC bán niên của GVR' (30/57) không có lệnh đo riêng; muốn có phải chạy repair với phạm vi "
        "không gồm BCTC đó.")

    S.h("10. Chép lại cả báo cáo (tab:chep)")
    S.n("rx_needed", "Phải chép lại", rx.get("phải chép lại", 0))
    S.n("rx_kept", "Bản chép lại tốt hơn nên được giữ",
        f"{rx.get('giữ bản chép lại', 0)} ({pct(rx.get('giữ bản chép lại', 0), rx.get('phải chép lại', 0), 0)})")
    S.n("rx_kept_clean", "... báo cáo được chép lại nay đạt mọi ràng buộc bắt buộc của nó",
        f"{rx.get('giữ và nay đạt mọi ràng buộc bắt buộc của báo cáo', 0)}/{rx.get('giữ bản chép lại', 0)}")
    S.n("rx_rot", "... nhờ xoay trang 180 độ", rx.get("giữ nhờ xoay 180 độ", 0))
    S.n("rx_not", "Không tốt hơn, giữ bản cũ", rx.get("không tốt hơn, giữ bản cũ", 0))

    S.h("11. Chi phí đọc một BCTC (tab:chiphi)")
    q4 = next((v for p, v in cs["periods"].items() if p == "Q4/2025"), None)
    if q4:
        S.n("cost_q4_n", "Số BCTC quý 4/2025 có bản ghi chi phí", q4["n"])
        S.n("cost_q4_mean", "Trung bình mỗi BCTC quý 4/2025 (USD)", vn(q4["mean"], 3))
        S.n("cost_q4_median", "Trung vị (USD)", vn(q4["median"], 3))
        S.n("cost_q4_p90", "90% số BCTC tốn dưới (USD)", vn(q4["p90"], 3))
        tb = q4["by_template"]
        S.n("cost_q4_bank", "Trung bình ở ngân hàng (USD)", vn(tb["bank"]["mean"], 3) if tb.get("bank") else None)
        S.n("cost_q4_corp", "Trung bình ở doanh nghiệp thường (USD)", vn(tb["corporate"]["mean"], 3) if tb.get("corporate") else None)
        steps_txt = "; ".join(f"{g} {vn(v[0], 1)}/{vn(v[1])}/{vn(v[2])}/{vn(v[3], 3)}" for g, v in q4["steps"].items())
        tot = [sum(v[i] for v in q4["steps"].values()) for i in range(4)]
        S.n("cost_q4_steps", "Theo bước, mỗi BCTC (lần gọi/token vào/token ra/USD)",
            f"{steps_txt}; tổng {vn(tot[0], 1)}/{vn(tot[1])}/{vn(tot[2])}/{vn(tot[3], 3)}")
    r = cs["rest"]
    S.n("cost_rest", "Các kỳ còn lại (USD)",
        f"{r['n']} BCTC: trung bình {vn(r['mean'], 3)}, trung vị {vn(r['median'], 3)}" if r else None)
    S.table(["Kỳ", "BCTC", "Trung bình", "Trung vị", "90%"],
            [[p, v["n"], vn(v["mean"], 3), vn(v["median"], 3), vn(v["p90"], 3)] for p, v in sorted(cs["periods"].items())])
    if cs["no_record"]:
        S.p(f"- BCTC trong phạm vi không có bản ghi chi phí: {cs['no_record']}")
    S.p("- Giá tính theo mô hình ghi trong bản ghi (như báo cáo). Bản ghi cộng dồn cả các lần đọc lại về sau (kiểm "
        "chéo kỳ, định vị ô), nên số của một kỳ cũ có thể nhích lên khi BCTC kỳ sau về và kích hoạt đọc lại; đọc lần hai "
        "tách riêng thành bước 'đọc lần hai'.")
    g = _find(r"^(\d+ bản ghi; .*)$", raw.get("cost", ""))
    if g:
        S.p(f"- Lệnh cost (mọi bản ghi, không theo phạm vi): {g[0]}")

    S.h("12. Nguồn đăng BCTC và thời gian tới khi có thẻ")
    g = _find(r"^(\d+) BCTC có ở cả hai nguồn: HOSE đăng trước (\d+), Vietstock đăng trước (\d+), cách nhau dưới 15 phút "
              r"(\d+); không thấy trên HOSE (\d+)", raw.get("sources", ""))
    S.n("src_both", "BCTC có ở cả hai nguồn", f"{g[0]}: HOSE trước {g[1]}, Vietstock trước {g[2]}, dưới 15 phút {g[3]}"
        if g else None)
    g = _find(r"^HOSE trừ Vietstock \(giờ\): (.*)$", raw.get("sources", ""))
    S.n("src_median", "HOSE trừ Vietstock (giờ, âm là HOSE sớm hơn)", g[0] if g else None)
    for line in raw.get("latency", "").splitlines():
        if line.strip() and not line.startswith("eval/"):
            S.p(f"- Độ trễ: {line.strip()}")
    S.p("- Thời gian tới khi có thẻ chưa có trong báo cáo (mục hướng phát triển); số ở đây để điền sau mùa quý 3.")

    S.h("13. Công văn giải trình (chưa có trong báo cáo kỹ thuật)")
    S.p(f"- Công văn có bản đọc lưu sẵn: {len(letters)}" + (f"; chưa đọc nên bỏ qua (chấm cần gọi mô hình): "
                                                             f"{letters_missing}" if letters_missing else ""))
    for line in raw.get("explanations", "").splitlines():
        if re.match(r"^\d+ công văn|^  (câu chính|nguyên nhân|cả phần):", line):
            S.p(f"- {line.strip()}")

    if "external" in raw:
        S.h("14. Đối chiếu với nguồn dữ liệu công khai")
        S.p("Xem raw/external.txt; số của nguồn ngoài chỉ dùng nội bộ, không hiển thị.")
        for line in raw["external"].splitlines()[-6:]:
            S.p(f"    {line}")

    S.h("Các bước đã chạy")
    S.table(["Bước", "Lệnh", "Giây", "Mã thoát", "Ghi chú"],
            [[n, f"`{c}`" if c else "", f"{s:.0f}", code, note] for n, c, s, code, note in steps.log])
    S.p(f"Tổng thời gian: {time.time() - t_start:.0f} giây. Không bước nào gọi mô hình (khóa API để trống trong tiến "
        "trình con; phép đếm trong lệnh chỉ đọc bản ghi đã lưu).")

    S.h("So với số báo cáo đang ghi")
    S.table(["Số liệu", "Báo cáo đang ghi", "Đo lại", "Giống"],
            [[label, rep, val, "có" if rep and rep.split(" (")[0] == val.split(" (")[0] else ("—" if not rep else "KHÁC")]
             for key, label, val, rep in S.rows if rep])

    text = "\n".join(S.lines) + "\n"
    (out / "summary.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"Đã ghi {out / 'summary.md'} và {steps.raw}/")


if __name__ == "__main__":
    main()
