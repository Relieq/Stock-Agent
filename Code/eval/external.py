"""Đối chiếu số trên thẻ Soi với một nguồn dữ liệu ngoài (CafeF), chỉ để đo độ chính xác nội bộ.

    python eval/external.py --year 2026 --period Q2 [--tickers FPT,VIC] [--verbose]

Số của CafeF KHÔNG được hiển thị hay lưu trên Soi (điều khoản nguồn ngoài, CLAUDE.md); lệnh này chỉ in kết quả ra màn
hình. Chạy sau mỗi mùa BCTC: bộ kiểm chứng ràng buộc kế toán bắt được ô đọc sai số, nhưng không bắt được ô đọc đúng số
mà lấy nhầm dòng (ví dụ VIC Q1/2026: BCTC không in mã 61/62, thẻ lấy nhầm dòng LNST tổng). Nguồn ngoài bắt loại lỗi đó.

Mỗi mã tải một trang KQKD theo quý của CafeF (4 quý tới kỳ đã chọn), nghỉ giữa các lần tải. So các chỉ tiêu:
  * doanh nghiệp: doanh thu thuần, lợi nhuận gộp, LNST công ty mẹ, theo đúng dòng trên trang CafeF;
  * ngân hàng, CTCK: trang CafeF xếp số vào nhãn mẫu doanh nghiệp nên không theo dòng được; chỉ xét số của Soi có
    xuất hiện trong cột cùng quý hay không.
Kết quả mỗi ô: khớp / lệch (in hai số) / không thấy (CafeF không có số so được). Khi lệch, mở BCTC gốc để phân xử:
số của Soi đã qua ràng buộc kế toán của chính BCTC nên lệch nhiều khi là do nguồn ngoài.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import unicodedata
from collections import Counter
from decimal import Decimal

import requests

from services.db import connect
from services.metrics import service

URL = "https://cafef.vn/du-lieu/bao-cao-tai-chinh/{t}/incsta/{y}/{q}/0/0/ket-qua-hoat-dong-kinh-doanh-{slug}.chn"
PAUSE = 2.0
# Dòng trên trang CafeF (mẫu doanh nghiệp) cho từng chỉ tiêu của thẻ
ROWS = {"revenue": re.compile(r"^3\. Doanh thu thuần"),
        "gross_profit": re.compile(r"^5\. Lợi nhuận gộp"),
        "npat_parent": re.compile(r"^19\. Lợi nhuận sau thuế công ty mẹ")}
METRICS = {"corporate": ("revenue", "gross_profit", "npat_parent"), "other": ("toi", "npat_parent")}   # CafeF không có dòng thu nhập lãi thuần


def slug(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower()).replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", "-", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip("-")


def amount(s: str) -> Decimal | None:
    s = re.sub(r"<[^>]+>", "", s).strip().replace(".", "")
    neg = s.startswith(("(", "-"))
    s = s.strip("()-")
    return (-1 if neg else 1) * Decimal(s) if s.isdigit() else None


def fetch(ticker: str, name: str, year: int, period: str) -> tuple[list[tuple[int, str]], list[tuple[str, list]]]:
    """(các cột (năm, kỳ), các dòng (nhãn, số theo cột)); trang lỗi -> hai danh sách rỗng."""
    r = requests.get(URL.format(t=ticker.lower(), y=year, q=period[1], slug=slug(name)),
                     headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    if r.status_code != 200:
        return [], []
    cols = [(int(y), f"Q{q}") for q, y in re.findall(r"Quý (\d)\s*-\s*(\d{4})", r.text)][:4]
    rows = []
    for tr in re.findall(r"<tr class=['\"]r_item[^>]*>(.*?)</tr>", r.text, re.S):
        tds = re.findall(r"<td class=\"b_r_c[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) > len(cols):
            rows.append((re.sub(r"<[^>]+>", "", tds[0]).strip(), [amount(x) for x in tds[1:len(cols) + 1]]))
    return cols, rows


def near(a: Decimal, b: Decimal) -> bool:
    """Bằng nhau trong mức làm tròn: CafeF làm tròn tới triệu với BCTC đơn vị triệu đồng, tới nghìn với phần còn lại."""
    return abs(a - b) <= (1_000_000 if b % 1_000_000 == 0 else 1_000)


def compare(conn, ticker: str, name: str, year: int, period: str) -> list[tuple]:
    cols, rows = fetch(ticker, name, year, period)
    out = []
    for i, (y, p) in enumerate(cols):
        doc = service.quarter_document(conn, ticker, y, p)
        got = service.card_for(conn, doc) if doc else None
        if not got or not got[1]["published"] or not got[0].supported:
            continue
        card = got[0]
        corporate = card.template not in ("TCTD", "CTCK")
        for key in METRICS["corporate" if corporate else "other"]:
            m = next((m for m in card.metrics if m.key == key), None)
            soi = m.q_cur.value if m else None
            if soi is None:
                continue
            if corporate:
                ext = next((v[i] for lab, v in rows if ROWS[key].search(lab)), None)
                res = ("không thấy", None) if ext is None else ("khớp", ext) if near(soi, ext) else ("lệch", ext)
            else:
                col = [v[i] for _, v in rows if v[i] is not None]
                res = ("khớp", soi) if any(near(soi, x) for x in col) else ("không thấy", None)
            out.append((ticker, f"{p}/{y}", key, res[0], soi, res[1]))
    return out


def ty(v: Decimal | None) -> str:
    return "-" if v is None else f"{v / Decimal(10**9):,.3f} tỷ"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--period", required=True, choices=("Q1", "Q2", "Q3", "Q4"), help="quý mới nhất trên trang CafeF")
    ap.add_argument("--tickers", help="danh sách mã, mặc định mọi mã đang theo dõi")
    ap.add_argument("--verbose", action="store_true", help="in cả các ô khớp")
    args = ap.parse_args()
    wanted = {t.strip().upper() for t in args.tickers.split(",")} if args.tickers else None
    results = []
    with connect() as conn:
        companies = conn.execute("SELECT ticker, name FROM companies WHERE tracked ORDER BY ticker").fetchall()
        for n, (ticker, name) in enumerate(c for c in companies if wanted is None or c[0] in wanted):
            if n:
                time.sleep(PAUSE)
            try:
                got = compare(conn, ticker, name, args.year, args.period)
            except requests.RequestException as e:
                print(f"{ticker}: không tải được trang ({e.__class__.__name__})")
                continue
            if not got:
                print(f"{ticker}: không có ô nào so được")
            for row in got:
                if args.verbose or row[3] != "khớp":
                    t, per, key, res, soi, ext = row
                    diff = f" | chênh {soi - ext:,.0f} đồng" if res == "lệch" else ""
                    print(f"{t} {per} {key}: {res} | Soi {ty(soi)} | ngoài {ty(ext)}{diff}", flush=True)
            results += got
    print()
    for key in sorted({r[2] for r in results}):
        c = Counter(r[3] for r in results if r[2] == key)
        print(f"{key}: " + ", ".join(f"{k} {v}" for k, v in c.most_common()))
    c = Counter(r[3] for r in results)
    print(f"Tổng {len(results)} ô: " + ", ".join(f"{k} {v}" for k, v in c.most_common()))


if __name__ == "__main__":
    main()
