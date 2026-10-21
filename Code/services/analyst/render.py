"""Dựng trang báo cáo: gắn liên kết từ mỗi con số trong lời văn tới dòng bảng số (và trang BCTC gốc), biểu đồ, ghi chú;
câu bị bỏ chỉ quản trị viên thấy. PDF dựng từ chính HTML của trang (WeasyPrint, chỉ có trong ảnh Docker)."""

from __future__ import annotations

from html import escape

from markupsafe import Markup

from services.analyst.charts import svg
from services.analyst.plan import Plan
from services.users import site_url

STATUS_TEXT = {
    "planning": "Đang hiểu yêu cầu…", "writing": "Đang tính số và viết…", "waiting_data": "Đang chờ đọc thêm BCTC",
    "awaiting_confirmation": "Cần bạn xác nhận đọc thêm BCTC", "needs_clarification": "Cần bạn nói rõ thêm",
    "done": "Xong", "failed": "Lỗi",
}


def sentence_html(text: str, links: list[dict]) -> Markup:
    out, pos = [], 0
    for l in sorted(links, key=lambda l: l["start"]):
        if l["start"] < pos:
            continue
        out.append(escape(text[pos:l["start"]], quote=False))
        out.append(f'<a class="num" href="#{escape(l["fact_id"])}">{escape(text[l["start"]:l["end"]], quote=False)}</a>')
        pos = l["end"]
    out.append(escape(text[pos:], quote=False))
    return Markup("".join(out))


def _source_links(sources: list[dict], absolute: bool) -> list[tuple[str, str]]:
    base = site_url() if absolute else ""
    seen, out = set(), []
    for s in sources:
        if s.get("page") and (s["document_id"], s["page"]) not in seen:
            seen.add((s["document_id"], s["page"]))
            out.append((f"trang {s['page']}", f"{base}/tai-lieu/{s['document_id']}/trang/{s['page']}.png"))
    return out


def context(row: dict, admin: bool, absolute: bool = False) -> dict:
    result = row.get("result") or {}
    draft, links = result.get("draft") or {"sections": []}, result.get("links") or {}
    sections = [{"heading": sec["heading"],
                 "sentences": [str(sentence_html(s["text"], links.get(f"{i}.{j}", [])))
                               for j, s in enumerate(sec["sentences"])]}
                for i, sec in enumerate(draft.get("sections", []))]
    facts = [{"id": f["id"], "text": f["text"], "links": _source_links(f.get("sources") or [], absolute)}
             for f in row.get("sheet") or []]
    plan = Plan.from_json(row["plan"]) if row.get("plan") else None
    log = row.get("guard_log") or {}
    return {"id": row["id"], "question": row["question"], "status": row["status"],
            "status_text": STATUS_TEXT.get(row["status"], row["status"]), "plan": plan,
            "plan_label": plan.label() if plan else "", "notes": row.get("notes") or [],
            "question_back": row.get("question_back"), "missing": row.get("missing") or [],
            "sections": sections, "facts": facts, "charts": [Markup(svg(c)) for c in row.get("charts") or []],
            "dropped": log.get("dropped", []) if admin else [], "attempts": log.get("attempts", []) if admin else [],
            "error": row.get("error") if admin else None, "created_at": row.get("created_at")}


def pdf(html: str, base_url: str) -> bytes:
    from weasyprint import HTML
    return HTML(string=html, base_url=base_url).write_pdf()
