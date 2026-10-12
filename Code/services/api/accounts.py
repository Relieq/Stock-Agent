"""Các trang cần đăng nhập: đăng nhập bằng link email, theo dõi mã, yêu cầu đọc BCTC / tải file lên, hàng duyệt."""

from __future__ import annotations

import os

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from services.alerts import notify_watchers
from services.db import connect
from services.extraction.verify import apply_manual_fix, approve_document
from services.ondemand import month_spend, monthly_budget, request_ticker, request_upload, used_today
from services.users import end_session, finish_login, set_watch, start_login, watchlist

COOKIE = "soi_session"
LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}
router = APIRouter()


def templates():
    from services.api.app import templates as t   # tránh import vòng
    return t


def user_of(request: Request):
    return getattr(request.state, "user", None)


def require_admin(request: Request):
    user = user_of(request)
    if user is None or not user.is_admin:
        raise HTTPException(403, "Chỉ người duyệt nội bộ")
    return user


def _back(path: str, msg: str | None = None) -> RedirectResponse:
    from urllib.parse import quote
    return RedirectResponse(path + (f"?tb={quote(msg)}" if msg else ""), status_code=303)


# ---- đăng nhập ----------------------------------------------------------------------------------------------------

@router.get("/dang-nhap")
def login_page(request: Request, next: str = "/mua-bctc"):
    return templates().TemplateResponse(request, "login.html", {"next": next, "sent": False, "dev_link": None})


@router.post("/dang-nhap")
def login_submit(request: Request, email: str = Form(...), next: str = Form("/mua-bctc")):
    with connect() as conn:
        delivered, link = start_login(conn, email)
    # Chưa cấu hình SMTP và đang chạy trên máy mình: hiện link ngay để dùng thử (không bao giờ hiện khi chạy trên mạng).
    # Trong Docker, yêu cầu đi qua cổng của Docker nên không thấy địa chỉ localhost: bật bằng DEV_LOGIN_LINK=1
    local = (request.client and request.client.host in LOCAL_HOSTS) or os.environ.get("DEV_LOGIN_LINK") == "1"
    dev_link = link if link and not delivered and local else None
    return templates().TemplateResponse(request, "login.html", {"next": next, "sent": True, "dev_link": dev_link})


@router.get("/dang-nhap/{token}")
def login_finish(request: Request, token: str, next: str = "/mua-bctc"):
    with connect() as conn:
        session = finish_login(conn, token)
    if session is None:
        return templates().TemplateResponse(request, "login.html", {
            "next": next, "sent": False, "dev_link": None, "error": "Link đã hết hạn hoặc đã được dùng. Hãy nhập email để nhận link mới."})
    resp = RedirectResponse(next if next.startswith("/") else "/mua-bctc", status_code=303)
    resp.set_cookie(COOKIE, session, max_age=30 * 86400, httponly=True, samesite="lax",
                    secure=os.environ.get("SITE_URL", "").startswith("https://"))
    return resp


@router.post("/dang-xuat")
def logout(request: Request):
    with connect() as conn:
        end_session(conn, request.cookies.get(COOKIE))
    resp = RedirectResponse("/dang-nhap", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp


# ---- theo dõi -----------------------------------------------------------------------------------------------------

@router.get("/theo-doi")
def watch_page(request: Request, tb: str | None = None):
    user = user_of(request)
    with connect() as conn:
        mine = watchlist(conn, user.id)
        companies = conn.execute("SELECT ticker, name FROM companies ORDER BY ticker").fetchall()
    return templates().TemplateResponse(request, "watch.html", {"mine": mine, "companies": companies, "tb": tb})


@router.post("/theo-doi")
def watch_submit(request: Request, ticker: str = Form(...), action: str = Form("add"), back: str = Form("/theo-doi")):
    user = user_of(request)
    ticker = ticker.strip().upper()
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM companies WHERE ticker = %s", (ticker,)).fetchone()
        if not exists:
            return _back("/theo-doi", f"Chưa có mã {ticker}. Mã ngoài danh sách: gửi yêu cầu đọc BCTC ở trang Yêu cầu.")
        set_watch(conn, user.id, ticker, action == "add")
    return RedirectResponse(back if back.startswith("/") else "/theo-doi", status_code=303)


# ---- yêu cầu đọc BCTC ngoài danh sách, tải file lên ------------------------------------------------------------------

def _ky(ky: str) -> tuple[int, str]:
    try:
        p, y = ky.strip().lower().split("-")
        return int(y), p.upper()
    except ValueError:
        raise HTTPException(400, "Kỳ không hợp lệ, ví dụ: q3-2026")


@router.get("/yeu-cau")
def requests_page(request: Request, tb: str | None = None):
    user = user_of(request)
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.id, r.kind, r.ticker, r.fiscal_year, r.fiscal_period, r.status, r.note, r.created_at,
                      r.document_id, d.owner_user_id IS NOT NULL
               FROM processing_requests r LEFT JOIN documents d ON d.id = r.document_id
               WHERE r.user_id = %s ORDER BY r.created_at DESC LIMIT 50""", (user.id,)).fetchall()
        used = used_today(conn, user.id)
    spend = month_spend()
    return templates().TemplateResponse(request, "requests.html", {
        "rows": rows, "used": used, "quota": user.daily_quota, "tb": tb,
        "over_budget": spend >= monthly_budget()})


@router.post("/yeu-cau/ma")
def request_ticker_submit(request: Request, ticker: str = Form(...), ky: str = Form(...)):
    user = user_of(request)
    year, period = _ky(ky)
    try:
        with connect() as conn:
            _, status = request_ticker(conn, user, ticker, year, period)
    except (ValueError, PermissionError) as e:
        return _back("/yeu-cau", str(e))
    return _back("/yeu-cau", "Đã có sẵn trong kho." if status == "done" else
                 "Đã nhận yêu cầu; hệ thống xử lý trong lượt canh kế tiếp (tối đa 15 phút) và báo qua email.")


@router.post("/yeu-cau/tai-len")
async def request_upload_submit(request: Request, file: UploadFile = File(...), ticker: str = Form(...),
                                ky: str = Form(...)):
    user = user_of(request)
    year, period = _ky(ky)
    data = await file.read()
    try:
        with connect() as conn:
            _, status = request_upload(conn, user, file.filename or "", data, ticker, year, period)
    except (ValueError, PermissionError) as e:
        return _back("/yeu-cau", str(e))
    return _back("/yeu-cau", "File này đã được đọc trước đây: dùng lại kết quả." if status == "done" else
                 "Đã nhận file; hệ thống sẽ tìm bản chính thức trên Vietstock trước, rồi đọc và báo qua email.")


# ---- hàng duyệt (nội bộ) -------------------------------------------------------------------------------------------

@router.get("/duyet")
def review_queue(request: Request):
    require_admin(request)
    with connect() as conn:
        rows = conn.execute(
            """SELECT d.id, d.ticker, d.fiscal_period, d.fiscal_year, d.doc_type, d.scope, d.title_raw,
                      (SELECT count(*) FROM validations v JOIN document_files f ON f.id = v.file_id
                       WHERE f.document_id = d.id AND (v.details->>'gate')::bool AND NOT v.passed),
                      d.owner_user_id IS NOT NULL
               FROM documents d WHERE d.status = 'needs_review'
               ORDER BY d.fiscal_year DESC, d.fiscal_period DESC, d.ticker""").fetchall()
    return templates().TemplateResponse(request, "review.html", {"rows": rows})


@router.post("/duyet/{doc_id}/sua")
def review_fix(request: Request, doc_id: int, statement: str = Form(...), row: int = Form(...),
               column: str = Form(...), value: str = Form(...), note: str = Form("")):
    user = require_admin(request)
    with connect() as conn:
        apply_manual_fix(conn, doc_id, statement, row, column, value.strip(), user.email, note)
    return RedirectResponse(f"/tai-lieu/{doc_id}", status_code=303)


@router.post("/duyet/{doc_id}/xuat-ban")
def review_approve(request: Request, doc_id: int):
    user = require_admin(request)
    with connect() as conn:
        approve_document(conn, doc_id, user.id, user.email)
        conn.commit()
        notify_watchers(conn, doc_id)
    return RedirectResponse("/duyet", status_code=303)
