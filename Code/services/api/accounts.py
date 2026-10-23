"""Các trang cần đăng nhập: đăng nhập bằng link email, theo dõi mã, yêu cầu đọc BCTC / tải file lên, hàng duyệt."""

from __future__ import annotations

import os

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse

from services.alerts import notify_watchers
from services.db import connect
from services import feedback
from services.extraction.verify import apply_manual_fix, approve_document, confirm_reading
from services.notify import notify_admin
from services.ondemand import month_spend, monthly_budget, request_ticker, request_upload, used_today
from services.users import (end_session, finish_login, invite, list_users, remove_user, send_invitation, set_watch,
                            start_login, update_user, watchlist)

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
        spend = month_spend(conn)
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


# ---- quản trị người dùng (nội bộ) ----------------------------------------------------------------------------------

@router.get("/quan-tri")
def admin_users(request: Request, tb: str | None = None):
    require_admin(request)
    with connect() as conn:
        users = list_users(conn)
    return templates().TemplateResponse(request, "admin_users.html", {"users": users, "tb": tb})


@router.get("/quan-tri/chi-phi")
def admin_costs(request: Request, tb: str | None = None):
    """Chi phí gọi mô hình: tháng này so với trần, theo ngày, theo bước, theo tài liệu, theo người yêu cầu; nhà cung
    cấp mô hình đang dùng và các lần tự chuyển sang nhà dự phòng."""
    require_admin(request)
    from services.costs import add_reports, recent_switches, report
    from services.llm import configured, provider_order, step_providers
    try:
        providers, order = configured(), provider_order()
    except RuntimeError as e:
        providers, order, tb = [], [], str(e)
    locate_provider = step_providers().get("page_classification", "")
    escalate_model = step_providers().get("repair_escalate", "")
    rep = report()
    doc_cost = {d.document_id: d.tally.usd for d in rep.docs}
    with connect() as conn:
        add_reports(rep, conn)
        rows = conn.execute(
            """SELECT u.email, count(*) AS requests,
                      count(*) FILTER (WHERE r.note IS DISTINCT FROM 'có sẵn trong kho') AS new_reads,
                      array_agg(DISTINCT r.document_id) FILTER (WHERE r.document_id IS NOT NULL
                                                              AND r.note IS DISTINCT FROM 'có sẵn trong kho')
               FROM processing_requests r JOIN users u ON u.id = r.user_id
               WHERE r.created_at >= date_trunc('month', now() AT TIME ZONE 'Asia/Ho_Chi_Minh') AT TIME ZONE 'Asia/Ho_Chi_Minh'
               GROUP BY u.email ORDER BY 2 DESC""").fetchall()
        names = dict(conn.execute(
            """SELECT id, fiscal_period || '/' || fiscal_year || ' · ' || CASE scope WHEN 'consolidated' THEN 'hợp nhất'
                      WHEN 'separate' THEN 'riêng' WHEN 'standalone' THEN 'duy nhất' ELSE scope END
               FROM documents WHERE id = ANY(%s)""", ([d.document_id for d in rep.docs[:15]],)).fetchall())
    users = [{"email": e, "requests": n, "new_reads": k, "usd": sum(doc_cost.get(d, 0) for d in (docs or []))}
             for e, n, k, docs in rows]
    days = sorted(((d, t) for d, t in rep.by_day.items() if d.startswith(rep.month)), reverse=True)
    budget = monthly_budget()
    with connect() as conn:
        from services.costs import requested_spend
        capped = requested_spend(conn, rep)
    return templates().TemplateResponse(request, "admin_costs.html", {
        "rep": rep, "budget": budget, "capped": capped, "share": min(100, capped / budget * 100) if budget else 0,
        "days": days, "months": sorted(rep.by_month.items(), reverse=True)[:6],
        "steps": sorted(rep.by_step_month.items(), key=lambda x: -x[1].usd),
        "steps_all": sorted(rep.by_step.items(), key=lambda x: -x[1].usd),
        "docs": rep.docs[:15], "names": names, "users": users, "tb": tb,
        "providers": providers, "order": order, "switches": recent_switches(), "locate_provider": locate_provider,
        "escalate_model": escalate_model, "escalate_options": [o for o in ESCALATE_OPTIONS if o.split(":")[0] in
                                                               [p for p, _ in providers]]})


@router.post("/quan-tri/mo-hinh")
def admin_set_provider(request: Request, provider: str = Form(...)):
    """Đổi nhà cung cấp chính (chỉ chọn trong các nhà đã cấu hình ở Code/.env). Nhà còn lại thành dự phòng: khi nhà
    chính hết tiền hay gặp lỗi, hệ thống tự chuyển sang nhà dự phòng."""
    me = require_admin(request)
    from services.llm import configured, write_settings
    if provider not in [p for p, _ in configured()]:
        return _back("/quan-tri/chi-phi", f"Nhà cung cấp {provider} chưa được cấu hình trong Code/.env")
    write_settings(llm_primary=provider, llm_primary_by=me.email)
    return _back("/quan-tri/chi-phi", f"Đã đặt {provider} làm nhà cung cấp chính; áp dụng cho các lần đọc BCTC từ giờ")


# Mô hình cho người đọc bậc cao (bước repair_escalate): chỉ được hỏi khi mô hình chính đọc lại vẫn không xác nhận được
# số mà ràng buộc kế toán đề xuất, nên chọn mô hình mạnh dù đắt hơn
ESCALATE_OPTIONS = ("anthropic:claude-opus-5-5", "anthropic:claude-sonnet-5-5", "openai:gpt-5.4")


@router.post("/quan-tri/mo-hinh-bac-cao")
def admin_set_escalate_model(request: Request, model: str = Form("")):
    me = require_admin(request)
    from services.llm import configured, step_providers, write_settings
    if model and (model not in ESCALATE_OPTIONS or model.split(":")[0] not in [p for p, _ in configured()]):
        return _back("/quan-tri/chi-phi", f"Không dùng được {model}: nhà cung cấp chưa cấu hình trong Code/.env")
    steps = step_providers() | {"repair_escalate": model}
    write_settings(llm_step_providers=steps, llm_step_providers_by=me.email)
    return _back("/quan-tri/chi-phi", "Người đọc bậc cao: " + (model if model else "tắt"))


@router.post("/quan-tri/mo-hinh-dinh-vi")
def admin_set_locate_provider(request: Request, provider: str = Form("")):
    """Bước định vị trang (tìm trang báo cáo, góc xoay) luôn ưu tiên một nhà cung cấp; để trống thì theo nhà chính."""
    me = require_admin(request)
    from services.llm import configured, step_providers, write_settings
    if provider and provider not in [p for p, _ in configured()]:
        return _back("/quan-tri/chi-phi", f"Nhà cung cấp {provider} chưa được cấu hình trong Code/.env")
    steps = step_providers() | {"page_classification": provider}
    write_settings(llm_step_providers=steps, llm_step_providers_by=me.email)
    return _back("/quan-tri/chi-phi", "Bước định vị trang: " + (f"luôn dùng {provider}" if provider else "theo nhà chính"))


@router.post("/quan-tri/moi")
def admin_invite(request: Request, email: str = Form(...), role: str = Form("user"), notify: str = Form("")):
    require_admin(request)
    try:
        with connect() as conn:
            user = invite(conn, email, role == "admin")
    except ValueError as e:
        return _back("/quan-tri", str(e))
    sent = send_invitation(user) if notify else False
    return _back("/quan-tri", f"Đã mời {user.email}" + ("; đã gửi email mời" if sent else
                 "; chưa gửi email (chưa cấu hình SMTP hoặc không chọn gửi)" if notify else ""))


@router.post("/quan-tri/{user_id}/sua")
def admin_update(request: Request, user_id: int, role: str = Form(...), daily_quota: int = Form(...)):
    require_admin(request)
    try:
        with connect() as conn:
            update_user(conn, user_id, role, daily_quota)
    except ValueError as e:
        return _back("/quan-tri", str(e))
    return _back("/quan-tri", "Đã cập nhật")


@router.post("/quan-tri/{user_id}/xoa")
def admin_remove(request: Request, user_id: int):
    me = require_admin(request)
    try:
        with connect() as conn:
            remove_user(conn, user_id, me.id)
    except ValueError as e:
        return _back("/quan-tri", str(e))
    return _back("/quan-tri", "Đã xóa người dùng")


# ---- góp ý ---------------------------------------------------------------------------------------------------------

@router.post("/gop-y")
def feedback_submit(request: Request, message: str = Form(""), page: str = Form("/")):
    user = user_of(request)
    page = feedback.safe_page(page)
    if user is None:
        return RedirectResponse(f"/dang-nhap?next={page}", status_code=303)
    sep = "&" if "?" in page else "?"
    try:
        with connect() as conn:
            feedback.save(conn, user.id, page, message)
    except ValueError as e:
        from urllib.parse import quote
        return RedirectResponse(f"{page}{sep}gopy_loi={quote(str(e))}#gop-y", status_code=303)
    notify_admin(f"[Soi] Góp ý từ {user.email}", feedback.email_body(user.email, page, message.strip()))
    return RedirectResponse(f"{page}{sep}gopy=1#gop-y", status_code=303)


@router.get("/quan-tri/gop-y")
def admin_feedback(request: Request):
    require_admin(request)
    with connect() as conn:
        items = feedback.recent(conn)
    return templates().TemplateResponse(request, "admin_feedback.html", {"items": items})


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


@router.post("/duyet/{doc_id}/dung-nhu-anh")
def review_confirm(request: Request, doc_id: int, statement: str = Form(...), key: str = Form(...),
                   column: str = Form(...)):
    """Ô cần xem ảnh: người duyệt đã xem ảnh, số đã đọc đúng như in."""
    user = require_admin(request)
    with connect() as conn:
        confirm_reading(conn, doc_id, statement, key, column, user.email)
    return RedirectResponse(f"/tai-lieu/{doc_id}", status_code=303)


@router.post("/duyet/{doc_id}/xuat-ban")
def review_approve(request: Request, doc_id: int):
    user = require_admin(request)
    with connect() as conn:
        approve_document(conn, doc_id, user.id, user.email)
        conn.commit()
        notify_watchers(conn, doc_id)
    return RedirectResponse("/duyet", status_code=303)
