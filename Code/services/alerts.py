"""Email cho người theo dõi: một email cho mỗi BCTC khi thẻ được xuất bản (kế hoạch MVP mục 2.4).

Không gửi thông báo theo giá hay theo mọi biến động; chỉ gửi khi BCTC của mã đang theo dõi đã kiểm chứng hoặc đã
duyệt tay. Bảng notifications bảo đảm mỗi người chỉ nhận một email cho một BCTC.
"""

from __future__ import annotations

import psycopg

from services.metrics.card import ty
from services.metrics.service import card_for
from services.notify import send_email
from services.users import site_url


def card_email(card, info) -> tuple[str, str]:
    """(tiêu đề, nội dung) của email báo thẻ mới."""
    m = {x.key: x for x in card.metrics}
    np = m.get("npat_parent")
    period = f"quý {card.period[1]}/{card.year}" if card.period.startswith("Q") else f"{card.period}/{card.year}"
    head = f"LNST {('−' if np.q_cur.value < 0 else '') + ty(np.q_cur.value)}" if np and np.q_cur.value is not None else ""
    subject = f"[Soi] {card.ticker} {period}: {head}" + (f" · {len(card.flags)} điểm cần xem kỹ" if card.flags else "")
    lines = [f"{card.ticker} - {info['name']}, BCTC {period} ({info['reviewed'].lower()}).", ""]
    for x in card.metrics[:3] if card.template != "TCTD" else card.metrics:
        if x.q_cur.value is None:
            continue
        lines.append(f"- {x.name} quý: {('−' if x.q_cur.value < 0 else '') + ty(x.q_cur.value)}"
                     + (f" ({x.q_change})" if x.q_change else ""))
    if card.plan:
        lines.append(f"- Lũy kế {card.plan['name']} đạt {card.plan['pct_text']} kế hoạch năm ({ty(card.plan['plan'])})")
    if card.flags:
        lines += ["", "Cần xem kỹ:"]
        lines += [f"- {f.title}: {f.detail}" for f in card.flags]
    lines += ["", f"Xem thẻ và trang BCTC gốc: {site_url()}/ma/{card.ticker}?ky={card.period.lower()}-{card.year}", "",
              "Thông tin từ BCTC đã công bố, đã kiểm chứng bằng ràng buộc kế toán. Không phải khuyến nghị đầu tư.",
              f"Bỏ theo dõi: {site_url()}/theo-doi"]
    return subject, "\n".join(lines)


def notify_watchers(conn: psycopg.Connection, document_id: int) -> int:
    """Gửi email cho người theo dõi mã của BCTC này nếu thẻ đã xuất bản. Trả về số email đã xử lý."""
    got = card_for(conn, document_id)
    if got is None:
        return 0
    card, info = got
    owner = conn.execute("SELECT owner_user_id FROM documents WHERE id = %s", (document_id,)).fetchone()[0]
    if not info["published"] or not card.supported or owner is not None:
        return 0
    users = conn.execute(
        """SELECT u.id, u.email FROM watchlist w JOIN users u ON u.id = w.user_id
           WHERE w.ticker = %s AND NOT EXISTS (SELECT 1 FROM notifications n
                 WHERE n.user_id = u.id AND n.document_id = %s AND n.channel = 'email')""",
        (card.ticker, document_id)).fetchall()
    if not users:
        return 0
    subject, body = card_email(card, info)
    for user_id, email in users:
        delivered = send_email(email, subject, body)
        conn.execute("INSERT INTO notifications (user_id, document_id, channel, delivered) VALUES (%s, %s, 'email', %s)",
                     (user_id, document_id, delivered))
    return len(users)
