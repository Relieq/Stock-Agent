"""Giao diện web.

Cho người dùng: bảng mùa BCTC (/mua-bctc/q3-2026), thẻ KQKD từng mã (/ma/FPT), API thẻ (/api/the/FPT).
Nội bộ: danh sách BCTC đã đọc (/noi-bo), số đã chép đặt cạnh ảnh trang gốc kèm các phép kiểm tra (/tai-lieu/{id}).
"""

from __future__ import annotations

from datetime import timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.api import data
from services.api.accounts import COOKIE, require_admin, router as accounts_router
from services.db import connect
from services.extraction.evidence import STATUS_LABELS
from services.ingestion.registry import raw_data_dir
from services.metrics import calendar as cal
from services.metrics import service as cards
from services.metrics import share
from services.metrics.card import card_dict
from services.metrics.card import ty as card_ty
from services.users import session_user, site_url, watchlist

VN_TZ = timezone(timedelta(hours=7))

HERE = Path(__file__).parent
app = FastAPI(title="Soi")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
app.include_router(accounts_router)

# Trang và ảnh chia sẻ thẻ KQKD công khai để mạng xã hội đọc được thẻ xem trước; chỉ thẻ đã kiểm chứng/duyệt tay
PUBLIC_PATHS = ("/dang-nhap", "/static/", "/chia-se/", "/anh/")


@app.middleware("http")
async def auth(request: Request, call_next):
    """Chỉ người được mời mới vào được (kế hoạch MVP mục 2.3); trang đăng nhập và tệp tĩnh thì công khai."""
    with connect() as conn:
        request.state.user = session_user(conn, request.cookies.get(COOKIE))
    path = request.url.path
    if request.state.user is None and not path.startswith(PUBLIC_PATHS):
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Cần đăng nhập"}, status_code=401)
        target = path + (f"?{request.url.query}" if request.url.query else "")
        from urllib.parse import quote
        return RedirectResponse(f"/dang-nhap?next={quote(target)}", status_code=303)
    return await call_next(request)

STATUS = {
    "verified": ("Đã kiểm chứng", "ok"),
    "needs_review": ("Cần duyệt tay", "warn"),
    "approved": ("Đã duyệt tay", "ok"),
    "failed": ("Lỗi", "bad"),
    "downloaded": ("Đã tải, chưa đọc", "muted"),
    "discovered": ("Chưa tải", "muted"),
    "extracting": ("Đang đọc", "muted"),
    "skipped": ("Bỏ qua", "muted"),
    "duplicate": ("Trùng file đã có", "muted"),
}
SCOPE = {"consolidated": "Hợp nhất", "separate": "Riêng", "standalone": "Duy nhất"}
COMPANY_KIND = {"corporate": "DN thường", "bank": "Ngân hàng", "securities": "CTCK", "insurance": "Bảo hiểm"}


def ty(v: Decimal | None) -> str:
    """Đồng -> tỷ đồng, kiểu Việt Nam (dấu chấm hàng nghìn, phẩy thập phân)."""
    if v is None:
        return "–"
    s = f"{abs(v) / Decimal(10**9):,.0f}".replace(",", ".")
    return f"({s})" if v < 0 else s


def dong(v: Decimal | None) -> str:
    if v is None:
        return "–"
    return f"{v:,.0f}".replace(",", ".")


templates.env.filters["ty"] = ty
templates.env.filters["dong"] = dong
templates.env.filters["tien"] = lambda v: "–" if v is None else ("−" if v < 0 else "") + card_ty(v)
templates.env.filters["gio"] = lambda t: t.astimezone(VN_TZ).strftime("%H:%M %d/%m/%Y") if t else "–"
templates.env.globals.update(STATUS=STATUS, SCOPE=SCOPE, COMPANY_KIND=COMPANY_KIND)


def _watcher_status() -> str | None:
    log = raw_data_dir() / "watcher.log"
    if not log.exists():
        return None
    lines = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if l.startswith("[")]
    return lines[-1] if lines else None


def _parse_ky(ky: str | None, conn) -> tuple[int, str]:
    """'q2-2026' -> (2026, 'Q2'); không có thì lấy quý mới nhất đã có BCTC được đọc."""
    if ky:
        try:
            p, y = ky.lower().split("-")
            if p.upper() in ("Q1", "Q2", "Q3", "Q4"):
                return int(y), p.upper()
        except ValueError:
            pass
        raise HTTPException(404, "Kỳ không hợp lệ, ví dụ: q3-2026")
    row = conn.execute("SELECT fiscal_year, fiscal_period FROM documents WHERE processed_at IS NOT NULL"
                       " AND doc_type = 'fs_quarter' ORDER BY fiscal_year DESC, fiscal_period DESC LIMIT 1").fetchone()
    if row is None:
        raise HTTPException(404, "Chưa có BCTC nào được đọc")
    return row[0], row[1]


def _quarters(conn) -> list[tuple[int, str]]:
    return conn.execute("SELECT DISTINCT fiscal_year, fiscal_period FROM documents WHERE doc_type = 'fs_quarter'"
                        " AND processed_at IS NOT NULL ORDER BY 1 DESC, 2 DESC").fetchall()


@app.get("/")
def home():
    return RedirectResponse("/mua-bctc")


@app.get("/mua-bctc")
@app.get("/mua-bctc/{ky}")
def season_page(request: Request, ky: str | None = None):
    with connect() as conn:
        year, period = _parse_ky(ky, conn)
        rows = cards.season(conn, year, period)
        quarters = _quarters(conn)
    return templates.TemplateResponse(request, "season.html", {
        "rows": rows, "year": year, "period": period, "quarters": quarters})


@app.get("/lich")
@app.get("/lich/{ky}")
def calendar_page(request: Request, ky: str | None = None):
    """Lịch công bố BCTC quý: mặc định là mùa đang diễn ra (quý vừa kết thúc), không phải quý mới nhất đã đọc."""
    with connect() as conn:
        year, period = _parse_ky(ky, conn) if ky else cal.current_quarter()
        entries = cal.calendar(conn, year, period)
        quarters = _quarters(conn)
    today = cal.today_vn()
    if (year, period) not in quarters:
        quarters = sorted([*quarters, (year, period)], reverse=True)
    groups = {k: [e for e in entries if e.status(today) == k] for k in ("overdue", "pending", "late", "published")}
    groups["pending"].sort(key=lambda e: (e.expected or e.deadline, e.ticker))
    for k in ("late", "published"):
        groups[k].sort(key=lambda e: e.published, reverse=True)
    return templates.TemplateResponse(request, "calendar.html", {
        "year": year, "period": period, "quarters": quarters, "groups": groups, "today": today,
        "quarter_end": cal.quarter_end(year, period), "total": len(entries)})


def _shared_card(ticker: str, ky: str):
    """Thẻ công khai để chia sẻ: chỉ BCTC quý chính thức (không phải bản tải lên riêng) đã kiểm chứng hoặc duyệt tay."""
    with connect() as conn:
        year, period = _parse_ky(ky, conn)
        doc_id = cards.quarter_document(conn, ticker.upper(), year, period)
        got = cards.card_for(conn, doc_id) if doc_id else None
    if got is None or not got[1]["published"] or not got[0].supported:
        raise HTTPException(404, "Chưa có thẻ đã kiểm chứng cho mã và kỳ này")
    return got


@app.get("/anh/{ticker}/{ky}.png")
def share_image(ticker: str, ky: str):
    card, info = _shared_card(ticker, ky)
    return Response(share.card_png(card, info["name"]), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@app.get("/chia-se/{ticker}/{ky}")
def share_page(request: Request, ticker: str, ky: str):
    card, info = _shared_card(ticker, ky)
    np = next((m for m in card.metrics if m.key == "npat_parent"), None)
    return templates.TemplateResponse(request, "share.html", {
        "card": card, "info": info, "ky": ky.lower(), "np": np, "site": site_url()})


@app.get("/ma/{ticker}")
def card_page(request: Request, ticker: str, ky: str | None = None):
    ticker = ticker.upper()
    with connect() as conn:
        year, period = _parse_ky(ky, conn)
        name = conn.execute("SELECT name FROM companies WHERE ticker = %s", (ticker,)).fetchone()
        if name is None:
            raise HTTPException(404, "Chưa theo dõi mã này")
        doc_id = cards.quarter_document(conn, ticker, year, period)
        got = cards.card_for(conn, doc_id) if doc_id else None
        quarters = _quarters(conn)
        watching = ticker in watchlist(conn, request.state.user.id)
    card, info = got if got else (None, None)
    return templates.TemplateResponse(request, "card.html", {
        "ticker": ticker, "name": name[0], "year": year, "period": period, "card": card, "info": info,
        "doc_id": doc_id, "quarters": quarters, "watching": watching, "private": False, "site": site_url()})


@app.get("/the/{doc_id}")
def card_by_document(request: Request, doc_id: int):
    """Thẻ theo mã tài liệu: dùng cho BCTC riêng do người dùng tải lên (chỉ người đó và người duyệt xem được)."""
    doc = _document(doc_id, request)
    with connect() as conn:
        got = cards.card_for(conn, doc_id)
    card, info = got if got else (None, None)
    return templates.TemplateResponse(request, "card.html", {
        "ticker": doc["ticker"], "name": doc["name"], "year": doc["year"], "period": doc["period"], "card": card,
        "info": info, "doc_id": doc_id, "quarters": [], "watching": False, "private": doc["owner"] is not None})


@app.get("/api/the/{ticker}")
def card_api(ticker: str, ky: str | None = None):
    with connect() as conn:
        year, period = _parse_ky(ky, conn)
        doc_id = cards.quarter_document(conn, ticker.upper(), year, period)
        got = cards.card_for(conn, doc_id) if doc_id else None
    if got is None:
        raise HTTPException(404, "Chưa có BCTC của kỳ này")
    card, info = got
    if not info["published"]:
        return {"ticker": ticker.upper(), "year": year, "period": period, "published": False,
                "status": info["status"]}
    return {"published": True, "info": {k: (str(v) if v is not None and k.endswith("_at") else v)
                                        for k, v in info.items()}, "card": card_dict(card)}


@app.get("/noi-bo")
def index(request: Request, year: int | None = None, period: str | None = None, all: bool = False):
    require_admin(request)
    with connect() as conn:
        periods = conn.execute(
            "SELECT DISTINCT fiscal_year, fiscal_period FROM documents WHERE doc_type = 'fs_quarter'"
            " AND fiscal_period IS NOT NULL ORDER BY 1 DESC, 2 DESC").fetchall()
        if year is None or period is None:
            latest = conn.execute(
                "SELECT fiscal_year, fiscal_period FROM documents WHERE processed_at IS NOT NULL"
                " ORDER BY fiscal_year DESC, fiscal_period DESC LIMIT 1").fetchone()
            year, period = latest or (periods[0] if periods else (None, None))
        scope_filter = "" if all else "AND d.scope IN ('consolidated', 'standalone')"
        rows = conn.execute(
            f"""
            SELECT d.id, d.ticker, c.name, c.template, d.scope, d.status, d.template_ver, d.title_raw,
                   d.source_listed_at, d.processed_at,
                   (SELECT count(*) FILTER (WHERE (v.details->>'gate')::bool AND v.passed) || '/' ||
                           count(*) FILTER (WHERE (v.details->>'gate')::bool)
                    FROM validations v JOIN document_files f ON f.id = v.file_id WHERE f.document_id = d.id)
            FROM documents d JOIN companies c ON c.ticker = d.ticker
            WHERE d.fiscal_year = %s AND d.fiscal_period = %s AND d.doc_type = 'fs_quarter'
              AND d.content_kind = 'full' {scope_filter}
            ORDER BY d.ticker, d.scope
            """, (year, period)).fetchall()
        totals = conn.execute(
            "SELECT count(*), count(*) FILTER (WHERE EXISTS (SELECT 1 FROM document_files f WHERE f.document_id = d.id)),"
            " count(*) FILTER (WHERE processed_at IS NOT NULL) FROM documents d").fetchone()

    docs = []
    conn = connect()
    for r in rows:
        rec = data.load_record(r[0]) if r[5] in ("verified", "needs_review") else None
        ev = data.evidence(conn, r[0]) if rec else None
        cov = None
        if ev:
            n = ev.counts()
            total = sum(n.values())
            unchecked = n["none"] + n["restated"] + n["second"] + n["second_differs"]
            cov = {"checked": (total - unchecked) / total if total else 0,
                   "conflict": n["conflict"] + n["second_differs"] + len(ev.missing),
                   "peers": ", ".join(p for _, p, _ in ev.peers)}
        docs.append({"id": r[0], "ticker": r[1], "name": r[2], "kind": r[3], "scope": r[4], "status": r[5],
                     "template": r[6], "title": r[7], "listed_at": r[8], "processed_at": r[9], "gate": r[10],
                     "head": data.headline(rec) if rec else {}, "has_record": rec is not None, "cov": cov})
    conn.close()
    return templates.TemplateResponse(request, "index.html", {
        "docs": docs, "year": year, "period": period, "periods": periods, "all": all,
        "totals": totals, "watcher": _watcher_status()})


def _document(doc_id: int, request: Request | None = None):
    with connect() as conn:
        row = conn.execute(
            """
            SELECT d.id, d.ticker, c.name, d.title_raw, d.source_url, d.status, d.scope, d.fiscal_year,
                   d.fiscal_period, f.storage_key, d.source_listed_at, d.processed_at, d.owner_user_id
            FROM documents d JOIN companies c ON c.ticker = d.ticker
            LEFT JOIN LATERAL (SELECT storage_key FROM document_files WHERE document_id = d.id
                               ORDER BY downloaded_at DESC LIMIT 1) f ON true
            WHERE d.id = %s
            """, (doc_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Không có tài liệu này")
    keys = ("id", "ticker", "name", "title", "source_url", "status", "scope", "year", "period", "storage_key",
            "listed_at", "processed_at", "owner")
    doc = dict(zip(keys, row))
    user = getattr(request.state, "user", None) if request else None
    if doc["owner"] is not None and (user is None or (user.id != doc["owner"] and not user.is_admin)):
        raise HTTPException(404, "Không có tài liệu này")   # BCTC riêng của người tải lên
    return doc


@app.get("/tai-lieu/{doc_id}")
def document(request: Request, doc_id: int):
    doc = _document(doc_id, request)
    record = data.load_record(doc_id)
    if record is None:
        raise HTTPException(404, "Tài liệu này chưa được đọc")
    with connect() as conn:
        evidence = data.evidence(conn, doc_id)
    return templates.TemplateResponse(request, "document.html", {
        "doc": doc, "record": record, "d": data.detail(record, evidence), "head": data.headline(record),
        "EVIDENCE": STATUS_LABELS, "admin": request.state.user is not None and request.state.user.is_admin})


@app.get("/tai-lieu/{doc_id}/trang/{page}.png")
def page_image(request: Request, doc_id: int, page: int):
    doc = _document(doc_id, request)
    record = data.load_record(doc_id)
    if record is None or not doc["storage_key"]:
        raise HTTPException(404)
    try:
        png = data.page_image(record, doc["storage_key"], page)
    except (IndexError, FileNotFoundError):
        raise HTTPException(404, "Không có trang này")
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


@app.get("/tai-lieu/{doc_id}/file")
def original_file(request: Request, doc_id: int):
    doc = _document(doc_id, request)
    if not doc["storage_key"]:
        raise HTTPException(404)
    path = raw_data_dir() / doc["storage_key"]
    return FileResponse(path, filename=path.name,
                        content_disposition_type="inline" if path.suffix.lower() == ".pdf" else "attachment")
