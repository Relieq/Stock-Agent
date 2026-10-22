"""Chi phí gọi mô hình (không gọi mô hình): theo tháng, theo ngày, theo bước, theo tài liệu. Dùng cho trang quản trị
"Chi phí" và lệnh `python -m services.extraction cost`.

Hai nguồn số liệu:
- Sổ chi phí (Data/raw/llm_calls.jsonl, từ 22/10/2026): mỗi lần gọi mô hình một dòng, chỉ ghi thêm, gồm cả lần đọc lại,
  đọc lần hai, công văn, báo cáo của agent và các lần chạy đo. Tổng theo ngày, tháng, bước lấy từ đây.
- Bản ghi đọc BCTC: mỗi tài liệu chỉ giữ lần đọc mới nhất, nên dùng để chia chi phí theo tài liệu (bảng BCTC tốn nhiều
  nhất, phần tính vào trần tháng) và cho thời gian trước khi có sổ. Số trước ngày mở sổ được chốt một lần vào
  Data/raw/llm_cost_baseline.json (`freeze_baseline`), không tính lại, để không cộng trùng với sổ; các lần đọc đã bị ghi
  đè trước ngày đó không còn dấu vết nên phần này thấp hơn thực tế.
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
    ledger_since: str | None = None     # có sổ chi phí: thời điểm bắt đầu tính theo sổ

    @property
    def this_month(self) -> Tally:
        return self.by_month.get(self.month, Tally())


def _records():
    for f in (raw_data_dir() / "extracted").glob("*/*.json"):
        try:
            yield json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue


def _record_entries():
    """(ngày, bước, mô hình, lần gọi, token vào, token ra, usd) từ các bản ghi đọc BCTC, và chi phí từng tài liệu."""
    entries, docs = [], []
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
        steps = dict(r.get("usage_by_step") or {})
        rest = {k: u.get(k, 0) - sum(s.get(k, 0) for s in steps.values())
                for k in ("calls", "input_tokens", "output_tokens")}
        if "usd" in u:
            rest["usd"] = u["usd"] - sum(s.get("usd", 0) for s in steps.values())
        if rest["calls"] > 0:
            steps[UNSPLIT] = rest
        # Bước không ghi tiền thì ước theo mô hình của bản ghi; khi bản ghi có tổng tiền thật, chia lại cho tổng các
        # bước bằng đúng tổng đó (bước có thể đã do nhà khác, giá khác trả lời)
        est = {step: su["usd"] if su.get("usd") is not None else
               (cost_usd(model, su.get("input_tokens", 0), su.get("output_tokens", 0)) or 0.0) for step, su in steps.items()}
        scale = u["usd"] / sum(est.values()) if u.get("usd") is not None and sum(est.values()) > 0 else 1.0
        for step, su in steps.items():
            entries.append((day, step, model, su.get("calls", 0), su.get("input_tokens", 0), su.get("output_tokens", 0),
                            est[step] * scale))
        docs.append(DocCost(r.get("document_id"), r.get("ticker", ""), day, doc))
    return entries, docs


def _report_entries(conn):
    """Chi phí agent báo cáo (bảng reports, theo bước)."""
    out = []
    for created, usage in conn.execute("SELECT created_at, usage FROM reports WHERE usage IS NOT NULL").fetchall():
        day = created.astimezone(VN).strftime("%Y-%m-%d")
        for step, u in (usage or {}).items():
            out.append((day, step, None, u.get("calls", 0), u.get("input_tokens", 0), u.get("output_tokens", 0),
                        u.get("usd", 0.0)))
    return out


def baseline_path():
    return raw_data_dir() / "llm_cost_baseline.json"


def _ledger_entries(since: str):
    from services.llm import ledger_path
    path = ledger_path()
    if not path.exists():
        return []
    out, start = [], datetime.fromisoformat(since)
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            c = json.loads(line)
            at = datetime.strptime(c["at"], "%Y-%m-%dT%H:%M:%S%z")
        except (ValueError, KeyError):
            continue
        if at < start:
            continue
        out.append((at.astimezone(VN).strftime("%Y-%m-%d"), c.get("step", "?"), c.get("model"), 1,
                    c.get("input_tokens", 0), c.get("output_tokens", 0), c.get("usd")))
    return out


def _fill(rep: Report, entries) -> None:
    for day, step, model, calls, ti, to, usd in entries:
        targets = [rep.total, rep.by_month.setdefault(day[:7], Tally()), rep.by_day.setdefault(day, Tally()),
                   rep.by_step.setdefault(step, Tally())]
        if day.startswith(rep.month):
            targets.append(rep.by_step_month.setdefault(step, Tally()))
        for t in targets:
            t.add(model, calls, ti, to, usd)


def report(now: datetime | None = None) -> Report:
    """Tổng theo ngày/tháng/bước: bản chốt trước ngày mở sổ + sổ chi phí; chưa chốt thì tính từ bản ghi (cách cũ, cần
    gọi thêm add_reports). Chi phí theo tài liệu luôn từ bản ghi."""
    now = (now or datetime.now(timezone.utc)).astimezone(VN)
    rep = Report(month=now.strftime("%Y-%m"))
    entries, rep.docs = _record_entries()
    base = baseline_path()
    if base.exists():
        b = json.loads(base.read_text(encoding="utf-8"))
        rep.ledger_since = b["cutoff"]
        _fill(rep, [tuple(e) for e in b["entries"]] + _ledger_entries(b["cutoff"]))
    else:
        _fill(rep, entries)
    rep.docs.sort(key=lambda d: -d.tally.usd)
    return rep


def freeze_baseline(conn) -> str:
    """Chốt chi phí trước lúc này (bản ghi + báo cáo agent, theo ngày và bước) rồi từ đó tính theo sổ. Chạy một lần."""
    if baseline_path().exists():
        return f"Đã chốt từ trước: {baseline_path()}"
    entries, _ = _record_entries()
    entries += _report_entries(conn)
    merged: dict[tuple[str, str], Tally] = {}
    for day, step, model, calls, ti, to, usd in entries:
        merged.setdefault((day, step), Tally()).add(model, calls, ti, to, usd)
    cutoff = datetime.now(timezone.utc).isoformat()
    baseline_path().write_text(json.dumps({"cutoff": cutoff, "entries": [
        [d, st, None, t.calls, t.input_tokens, t.output_tokens, round(t.usd, 6)] for (d, st), t in sorted(merged.items())]},
        ensure_ascii=False, indent=0), encoding="utf-8")
    return f"Chốt {sum(t.usd for t in merged.values()):.2f} USD trước {cutoff}; từ nay tính theo sổ chi phí"


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


def add_reports(rep: Report, conn) -> None:
    """Cộng chi phí của agent báo cáo (bảng reports, theo bước) vào bảng chi phí: tổng, tháng, ngày, bước. Đã có sổ chi
    phí thì không cộng (sổ đã gồm các lần gọi của agent)."""
    if rep.ledger_since:
        return
    _fill(rep, _report_entries(conn))


def report_spend(conn) -> float:
    """Chi phí agent báo cáo trong tháng (tính vào trần tháng cùng phần đọc theo yêu cầu)."""
    rows = conn.execute(f"SELECT usage FROM reports WHERE usage IS NOT NULL AND created_at >= {MONTH_START}").fetchall()
    return sum(u.get("usd", 0.0) for (usage,) in rows for u in (usage or {}).values())


def requested_spend(conn, rep: Report | None = None) -> float:
    """Chi phí tính vào trần tháng: các BCTC đọc theo yêu cầu người dùng và agent báo cáo. Đọc theo lịch cho các mã đang
    theo dõi (VN30...) không tính, vì người vận hành báo trước và duyệt chi phí từng đợt."""
    rep = rep or report()
    docs = requested_documents(conn)
    return sum(d.tally.usd for d in rep.docs if d.document_id in docs) + report_spend(conn)
