"""Chi phí gọi mô hình, tổng hợp từ các bản ghi trích xuất (không gọi mô hình): theo tháng, theo ngày, theo bước, theo
tài liệu. Dùng cho trang quản trị "Chi phí" và lệnh `python -m services.extraction cost`.

Mỗi bản ghi tính vào ngày bắt đầu đọc (`started_at`, giờ Việt Nam), kể cả các lần đọc lại về sau. Bản ghi cũ chưa ghi
số liệu theo bước thì phần chênh nằm ở bước "(chưa ghi theo bước)".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from services.ingestion.registry import raw_data_dir
from services.llm import cost_usd

VN = timezone(timedelta(hours=7))
UNSPLIT = "(chưa ghi theo bước)"


@dataclass
class Tally:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0

    def add(self, model: str | None, calls: int, ti: int, to: int, usd: float | None = None) -> None:
        """`usd`: chi phí đã tính theo từng lần gọi (bản ghi từ 17/10/2026, khi có thể đã chuyển nhà cung cấp giữa
        chừng); bản ghi cũ không có thì ước tính theo mô hình của bản ghi."""
        self.calls += calls
        self.input_tokens += ti
        self.output_tokens += to
        self.usd += usd if usd is not None else (cost_usd(model, ti, to) or 0.0)


@dataclass
class DocCost:
    document_id: int
    ticker: str
    day: str
    tally: Tally


@dataclass
class Report:
    total: Tally = field(default_factory=Tally)
    by_month: dict[str, Tally] = field(default_factory=dict)
    by_day: dict[str, Tally] = field(default_factory=dict)
    by_step: dict[str, Tally] = field(default_factory=dict)
    by_step_month: dict[str, Tally] = field(default_factory=dict)
    docs: list[DocCost] = field(default_factory=list)
    month: str = ""

    @property
    def this_month(self) -> Tally:
        return self.by_month.get(self.month, Tally())


def _records():
    for f in (raw_data_dir() / "extracted").glob("*/*.json"):
        try:
            yield json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue


def report(now: datetime | None = None) -> Report:
    now = (now or datetime.now(timezone.utc)).astimezone(VN)
    rep = Report(month=now.strftime("%Y-%m"))
    for r in _records():
        model = r.get("model")
        u = r.get("usage") or {}
        if not u.get("calls"):
            continue
        try:
            day = datetime.fromisoformat(str(r.get("started_at"))).astimezone(VN).strftime("%Y-%m-%d")
        except ValueError:
            day = "?"
        doc = Tally()
        doc.add(model, u.get("calls", 0), u.get("input_tokens", 0), u.get("output_tokens", 0), u.get("usd"))
        for t in (rep.total, rep.by_month.setdefault(day[:7], Tally()), rep.by_day.setdefault(day, Tally())):
            t.add(model, u.get("calls", 0), u.get("input_tokens", 0), u.get("output_tokens", 0), u.get("usd"))
        steps = dict(r.get("usage_by_step") or {})
        rest = {k: u.get(k, 0) - sum(s.get(k, 0) for s in steps.values())
                for k in ("calls", "input_tokens", "output_tokens")}
        if "usd" in u:
            rest["usd"] = u["usd"] - sum(s.get("usd", 0) for s in steps.values())
        if rest["calls"] > 0:
            steps[UNSPLIT] = rest
        for step, su in steps.items():
            targets = [rep.by_step.setdefault(step, Tally())]
            if day.startswith(rep.month):
                targets.append(rep.by_step_month.setdefault(step, Tally()))
            for t in targets:
                t.add(model, su.get("calls", 0), su.get("input_tokens", 0), su.get("output_tokens", 0), su.get("usd"))
        rep.docs.append(DocCost(r.get("document_id"), r.get("ticker", ""), day, doc))
    rep.docs.sort(key=lambda d: -d.tally.usd)
    return rep


def recent_switches(limit: int = 10) -> list[dict]:
    """Các lần tự chuyển nhà cung cấp mô hình gần nhất (ghi trong bản ghi đọc BCTC), mới nhất trước."""
    out = []
    for r in _records():
        for s in r.get("llm_switches") or []:
            out.append(s | {"document_id": r.get("document_id"), "ticker": r.get("ticker", "")})
    return sorted(out, key=lambda s: s.get("at", ""), reverse=True)[:limit]


MONTH_START = "date_trunc('month', now() AT TIME ZONE 'Asia/Ho_Chi_Minh') AT TIME ZONE 'Asia/Ho_Chi_Minh'"


def requested_documents(conn) -> set[int]:
    """BCTC phải đọc mới vì người dùng yêu cầu (mã ngoài danh sách, file tải lên) trong tháng này; yêu cầu trả ngay từ
    kho không tính."""
    return {d for (d,) in conn.execute(
        f"""SELECT DISTINCT document_id FROM processing_requests
            WHERE document_id IS NOT NULL AND note IS DISTINCT FROM 'có sẵn trong kho'
              AND created_at >= {MONTH_START}""")}


def requested_spend(conn, rep: Report | None = None) -> float:
    """Chi phí tính vào trần tháng: chỉ các BCTC đọc theo yêu cầu người dùng. Đọc theo lịch cho các mã đang theo dõi
    (VN30...) không tính, vì người vận hành báo trước và duyệt chi phí từng đợt."""
    rep = rep or report()
    docs = requested_documents(conn)
    return sum(d.tally.usd for d in rep.docs if d.document_id in docs)
