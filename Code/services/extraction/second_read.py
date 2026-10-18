"""Người đọc thứ hai cho các ô không phép kiểm nào phủ.

Phép cộng không thấy lỗi ở dòng không thuộc phép cộng nào (lãi trên cổ phiếu, mục ngoài bảng của ngân hàng, khoản
"trong đó") và không thấy cả khối dòng bị chép lệch xuống một dòng khi khối đó nằm ngoài mọi tổng. Một mô hình khác hãng
với lần đọc đầu chép lại cả báo cáo có ô như vậy; ô hai lần đọc khác nhau được đánh dấu cần xem lại
(evidence.cell_status), không chặn BCTC: người đọc thứ hai có thể yếu hơn người đọc đầu.

Đo trên 119 BCTC đã đọc (eval/second_read.py): ở nhóm ô đã có phép kiểm xác nhận, hai lần đọc trùng nhau 97,8%; ở nhóm
chưa có phép kiểm, mọi chỗ khác chữ số đều là lỗi của lần đọc đầu.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services.extraction import prompts
from services.extraction.pipeline import (
    _extract_detail,
    _extract_image,
    _finalize,
    _load_record,
    _rotation,
    open_record_pdf,
    track_usage,
)
from services.llm import VisionClient

STATEMENTS = ("BS", "IS", "CF")


def statement_pages(record: dict) -> dict[str, list[int]]:
    """Trang của từng báo cáo: trang lần đọc đầu đã chép (theo dòng) cộng trang bước định vị đã chọn."""
    chosen = next((c for c in record.get("candidates", []) if c.get("name") == record.get("chosen")), {})
    out = {}
    for st in STATEMENTS:
        pages = {int(p) for p in (chosen.get("statement_pages") or {}).get(st, [])}
        pages |= {int(r["page"]) for r in record.get("raw", {}).get(st, {}).get("rows", []) if r.get("page")}
        if pages:
            out[st] = sorted(pages)
    return out


def unchecked_statements(conn, document_id: int, record: dict) -> set[str]:
    """Báo cáo còn ô chưa được phép kiểm nào xác nhận (trạng thái "none" khi chưa có lần đọc thứ hai)."""
    from services.extraction.evidence import document_evidence

    rec = {k: v for k, v in record.items() if k != "second_read"}
    ev = document_evidence(conn, document_id, load=lambda d: rec if d == document_id else _try(conn, d))
    if ev is None:
        return set()
    return {st for (st, _, _), s in ev.status.items() if s["status"] == "none"}


def _try(conn, document_id: int) -> dict | None:
    try:
        return _load_record(conn, document_id)
    except RuntimeError:
        return None


def read(record: dict, client: VisionClient, doc, statements: set[str] | None = None,
         provider: str | None = None) -> dict | None:
    """Chép lại các báo cáo bằng nhà cung cấp khác hãng với lần đọc đầu (hoặc `provider` khi đo thử). None nếu chỉ
    cấu hình một nhà cung cấp."""
    provider = provider or client.other_than(record.get("provider"))
    if provider is None:
        return None
    raw, models = {}, set()
    usd_before = client.usage.usd
    for st, pages in statement_pages(record).items():
        if statements is not None and st not in statements:
            continue
        images = [(f"Trang {p}", _extract_image(doc, p, _rotation(record, p))) for p in pages]
        raw[st] = client.json_from_images(prompts.extract_prompt(st), images, prompts.extract_schema(st),
                                          f"statement_{st}", step=f"second_read_{st}",
                                          detail=_extract_detail(doc, pages), provider=provider)
        models.add(client.last_model)
    return {"first_reader": f"{record.get('provider')}/{record.get('model')}", "second_reader": sorted(models),
            "usd": client.usage.usd - usd_before, "at": datetime.now(timezone.utc).isoformat(), "raw": raw}


def second_read_document(conn, document_id: int, client: VisionClient, force: bool = False) -> dict | None:
    """Đọc lần hai các báo cáo còn ô chưa kiểm được và lưu vào bản ghi. Trả về record["second_read"] mới, None nếu
    không cần đọc (đã có lần đọc thứ hai, không còn ô chưa kiểm, hoặc không có nhà cung cấp thứ hai)."""
    record = _load_record(conn, document_id)
    if record.get("second_read") and not force:
        return None
    statements = unchecked_statements(conn, document_id, record)
    if not statements:
        return None
    doc = open_record_pdf(conn, record)
    with track_usage(record, client):
        second = read(record, client, doc, statements)
    if second is None:
        return None
    record["second_read"] = second
    _finalize(conn, record)
    return second


def after_extraction(conn, document_id: int, client: VisionClient) -> str | None:
    """Bước cuối của bộ canh sau khi đọc xong một BCTC: lỗi ở đây không làm hỏng kết quả đã lưu. Trả về một dòng mô
    tả cho thư báo quản trị, None nếu không cần đọc lần hai."""
    from services.extraction.evidence import document_evidence

    try:
        second = second_read_document(conn, document_id, client)
    except Exception as e:  # lỗi mạng, hết tiền ở nhà cung cấp thứ hai...
        conn.rollback()
        return f"đọc lần hai lỗi ({e})"
    if second is None:
        return None
    conn.commit()
    ev = document_evidence(conn, document_id)
    n = sum(s["status"] == "second_differs" for s in ev.status.values()) if ev else 0
    return (f"đọc lần hai {len(second['raw'])} báo cáo ({second['usd']:.3f} USD): "
            + (f"{n} ô hai lần đọc khác nhau, cần xem lại" if n else "không ô nào khác"))
