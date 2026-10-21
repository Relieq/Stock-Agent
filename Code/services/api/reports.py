"""Trang báo cáo theo yêu cầu (agent): gõ câu hỏi, xem báo cáo, xác nhận đọc thêm BCTC, tải PDF. Chỉ người tạo và quản
trị viên xem được báo cáo."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from services.analyst import render, report
from services.api.accounts import _back, templates, user_of
from services.db import connect
from services.users import site_url

router = APIRouter()
SAMPLES = ["So sánh kết quả kinh doanh quý 3/2026 của VCB và TCB",
           "Đánh giá kết quả kinh doanh quý gần nhất của FPT so với cùng kỳ",
           "LNST quý 3/2026 của TCB đứng thứ mấy trong các ngân hàng?"]


def can_view(row: dict, user) -> bool:
    return user is not None and (user.is_admin or row["user_id"] == user.id)


def _row(rid: int, request: Request) -> dict:
    with connect() as conn:
        row = report.get(conn, rid)
    if row is None or not can_view(row, user_of(request)):
        raise HTTPException(404, "Không có báo cáo này")
    return row


def _run_in_background(rid: int, resume=None, expect: str | None = None) -> None:
    """Chạy nền: lỗi đọc trạng thái đồ thị chỉ ghi nhật ký, không làm hỏng yêu cầu web (báo cáo kẹt sẽ được bộ canh
    đánh dấu lỗi)."""
    try:
        report.run(rid, resume, expect=expect)
    except Exception as e:      # noqa: BLE001
        print(f"[báo cáo] chạy nền báo cáo {rid} lỗi: {e}")


@router.get("/bao-cao")
def reports_page(request: Request, tb: str | None = None):
    user = user_of(request)
    with connect() as conn:
        rows = report.mine(conn, user.id)
    return templates().TemplateResponse(request, "reports.html", {"rows": rows, "samples": SAMPLES, "tb": tb,
                                                                  "limit": report.REPORTS_PER_DAY})


@router.post("/bao-cao")
def reports_submit(request: Request, background: BackgroundTasks, question: str = Form(...)):
    user = user_of(request)
    if not question.strip():
        return _back("/bao-cao", "Bạn gõ câu hỏi trước đã.")
    try:
        with connect() as conn:
            rid = report.create(conn, user, question)
            conn.commit()
    except PermissionError as e:
        return _back("/bao-cao", str(e))
    background.add_task(_run_in_background, rid)
    return RedirectResponse(f"/bao-cao/{rid}", status_code=303)


@router.get("/bao-cao/{rid}")
def report_page(request: Request, rid: int):
    row = _row(rid, request)
    r = render.context(row, admin=user_of(request).is_admin)
    return templates().TemplateResponse(request, "report.html", {"r": r, "refresh": row["status"] in report.RUNNING})


@router.post("/bao-cao/{rid}/xac-nhan")
def report_confirm(request: Request, background: BackgroundTasks, rid: int, yes: int = Form(...)):
    _row(rid, request)
    # Đặt trạng thái tạm để trang không hiện lại nút trong lúc chạy nền; chỉ một lần bấm đổi được trạng thái (điều kiện
    # trong câu lệnh), bấm lặp thì bỏ qua. Chạy tiếp còn được chặn thêm bằng điểm dừng (expect) trong luồng.
    with connect() as conn:
        moved = conn.execute("UPDATE reports SET status = %s WHERE id = %s AND status = 'awaiting_confirmation'",
                             ("waiting_data" if yes else "writing", rid)).rowcount
        conn.commit()
    if moved:
        background.add_task(_run_in_background, rid, bool(yes), "missing")
    return RedirectResponse(f"/bao-cao/{rid}", status_code=303)


@router.get("/bao-cao/{rid}/pdf")
def report_pdf(request: Request, rid: int):
    row = _row(rid, request)
    if row["status"] != "done":
        raise HTTPException(409, "Báo cáo chưa xong")
    html = templates().get_template("report_pdf.html").render(r=render.context(row, admin=False, absolute=True),
                                                              site=site_url())
    return Response(render.pdf(html, site_url()), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="soi-bao-cao-{rid}.pdf"'})
