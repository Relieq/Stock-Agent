"""Giao diện web. Bản đầu chỉ để xem lại kết quả đọc BCTC: số đã chép đặt cạnh ảnh trang gốc, kèm các phép kiểm tra."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from services.api import data
from services.db import connect
from services.ingestion.registry import raw_data_dir

HERE = Path(__file__).parent
app = FastAPI(title="Soi")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")

STATUS = {
    "verified": ("Đã kiểm chứng", "ok"),
    "needs_review": ("Cần duyệt tay", "warn"),
    "failed": ("Lỗi", "bad"),
    "downloaded": ("Đã tải, chưa đọc", "muted"),
    "discovered": ("Chưa tải", "muted"),
    "extracting": ("Đang đọc", "muted"),
    "skipped": ("Bỏ qua", "muted"),
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
templates.env.globals.update(STATUS=STATUS, SCOPE=SCOPE, COMPANY_KIND=COMPANY_KIND)


def _watcher_status() -> str | None:
    log = raw_data_dir() / "watcher.log"
    if not log.exists():
        return None
    lines = [l for l in log.read_text(encoding="utf-8", errors="replace").splitlines() if l.startswith("[")]
    return lines[-1] if lines else None


@app.get("/")
def index(request: Request, year: int | None = None, period: str | None = None, all: bool = False):
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
    for r in rows:
        rec = data.load_record(r[0]) if r[5] in ("verified", "needs_review") else None
        docs.append({"id": r[0], "ticker": r[1], "name": r[2], "kind": r[3], "scope": r[4], "status": r[5],
                     "template": r[6], "title": r[7], "listed_at": r[8], "processed_at": r[9], "gate": r[10],
                     "head": data.headline(rec) if rec else {}, "has_record": rec is not None})
    return templates.TemplateResponse(request, "index.html", {
        "docs": docs, "year": year, "period": period, "periods": periods, "all": all,
        "totals": totals, "watcher": _watcher_status()})


def _document(doc_id: int):
    with connect() as conn:
        row = conn.execute(
            """
            SELECT d.id, d.ticker, c.name, d.title_raw, d.source_url, d.status, d.scope, d.fiscal_year,
                   d.fiscal_period, f.storage_key, d.source_listed_at, d.processed_at
            FROM documents d JOIN companies c ON c.ticker = d.ticker
            LEFT JOIN LATERAL (SELECT storage_key FROM document_files WHERE document_id = d.id
                               ORDER BY downloaded_at DESC LIMIT 1) f ON true
            WHERE d.id = %s
            """, (doc_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Không có tài liệu này")
    keys = ("id", "ticker", "name", "title", "source_url", "status", "scope", "year", "period", "storage_key",
            "listed_at", "processed_at")
    return dict(zip(keys, row))


@app.get("/tai-lieu/{doc_id}")
def document(request: Request, doc_id: int):
    doc = _document(doc_id)
    record = data.load_record(doc_id)
    if record is None:
        raise HTTPException(404, "Tài liệu này chưa được đọc")
    return templates.TemplateResponse(request, "document.html", {
        "doc": doc, "record": record, "d": data.detail(record), "head": data.headline(record)})


@app.get("/tai-lieu/{doc_id}/trang/{page}.png")
def page_image(doc_id: int, page: int):
    doc = _document(doc_id)
    record = data.load_record(doc_id)
    if record is None or not doc["storage_key"]:
        raise HTTPException(404)
    try:
        png = data.page_image(record, doc["storage_key"], page)
    except (IndexError, FileNotFoundError):
        raise HTTPException(404, "Không có trang này")
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


@app.get("/tai-lieu/{doc_id}/file")
def original_file(doc_id: int):
    doc = _document(doc_id)
    if not doc["storage_key"]:
        raise HTTPException(404)
    path = raw_data_dir() / doc["storage_key"]
    return FileResponse(path, filename=path.name,
                        content_disposition_type="inline" if path.suffix.lower() == ".pdf" else "attachment")
