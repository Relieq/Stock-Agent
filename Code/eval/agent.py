"""Đo agent báo cáo (Baocao/dinh-huong/agent-bao-cao.md mục 11) trên bộ câu eval/data/agent_requests.jsonl.

    python eval/agent.py plan --provider anthropic [--limit 5]   # hiểu yêu cầu: so kế hoạch với đáp án
    python eval/agent.py write --provider anthropic [--limit 5]  # viết + kiểm số theo kế hoạch đúng (không đọc thêm BCTC)
    python eval/agent.py inject                                  # cấy lỗi vào câu đã đạt, đo bộ kiểm tra bắt được bao nhiêu
    python eval/agent.py summary                                 # in lại kết quả đã lưu, không gọi mô hình

Kết quả gọi mô hình lưu ở Data/raw/agent_eval/<nhà cung cấp>/: chạy lại chỉ chấm lại. Ngày cố định 21/10/2026 để các câu
"năm nay", "quý vừa rồi" có cùng đáp án ở mọi lần đo. Hai nhà cung cấp chạy cùng bộ câu, cùng bảng số.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

TODAY = date(2026, 10, 21)
GOLDEN = Path(__file__).resolve().parent / "data" / "agent_requests.jsonl"     # nằm trong Code/ để container thấy
FIELDS = ("kind", "tickers", "year", "period", "basis", "advice_request")


def load_golden(limit: int | None = None) -> list[dict]:
    rows = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[:limit] if limit else rows


def score_plan(got: dict, expect: dict) -> dict[str, bool]:
    out = {}
    for f in FIELDS:
        if f == "tickers":
            out[f] = sorted(t.strip().upper() for t in got.get(f, [])) == sorted(expect[f])
        else:
            out[f] = got.get(f) == expect[f]
    return out


def mutations(text: str) -> list[tuple[str, str]]:
    """Các cách làm sai một câu đã đạt: đổi số (lệch 10%), đảo tăng/giảm, đảo so sánh, đảo cao nhất/thấp nhất, chèn câu
    khuyến nghị, chèn mã lạ."""
    from services.analyst.guard import numbers
    out = []
    ns = [n for n in numbers(text) if n.kind != "plain"]
    if ns:
        n = ns[0]
        v = abs(n.value / n.scale) * 11 / 10
        s = f"{v:,.{max(n.decimals, 1)}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        raw = text[n.start:n.end]
        digits = re.search(r"\d[\d.,]*", raw).group(0)
        out.append(("number", text[:n.start] + raw.replace(digits, s, 1) + text[n.end:]))
    swaps = {"direction": [("tăng", "giảm"), ("giảm", "tăng")],
             "comparison": [("nhanh hơn", "chậm hơn"), ("chậm hơn", "nhanh hơn"), ("cao hơn", "thấp hơn"),
                            ("thấp hơn", "cao hơn"), ("cao nhất", "thấp nhất"), ("thấp nhất", "cao nhất")]}
    for kind, pairs in swaps.items():
        for a, b in pairs:
            if re.search(rf"\b{a}\b", text):
                out.append((kind, re.sub(rf"\b{a}\b", b, text, count=1)))
                break
    out.append(("advice", text.rstrip(".") + "; nhà đầu tư nên mua cổ phiếu này."))
    out.append(("foreign_ticker", text.rstrip(".") + ", tốt hơn HPG."))
    return out


def client_for(provider: str):
    from services.llm import VisionClient, _provider_config, configured
    model = dict(configured()).get(provider)
    return VisionClient(_provider_config(provider, model))


def out_dir(provider: str) -> Path:
    from services.ingestion.registry import raw_data_dir
    d = raw_data_dir() / "agent_eval" / provider
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_plan(args) -> None:
    from services.analyst.plan import parse_request
    from services.db import connect
    client = None
    with connect() as conn:
        companies = conn.execute("SELECT ticker, name FROM companies WHERE tracked ORDER BY ticker").fetchall()
    tally, usd = Counter(), 0.0
    rows = load_golden(args.limit)
    for g in rows:
        cache = out_dir(args.provider) / f"{g['id']}_plan.json"
        if cache.exists():
            got = json.loads(cache.read_text(encoding="utf-8"))
        else:
            client = client or client_for(args.provider)
            before = client.usage.usd
            got = parse_request(client, g["q"], TODAY, companies).to_json() | {"_usd": client.usage.usd - before}
            cache.write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
        usd += got.get("_usd", 0.0)
        s = score_plan(got, g["expect"])
        tally["all"] += all(s.values())
        for f, ok in s.items():
            tally[f] += ok
        if not all(s.values()):
            print(f"  [{g['id']}] {g['q']}: sai {[f for f, ok in s.items() if not ok]} -> {got}")
    n = len(rows)
    print(f"{args.provider}: kế hoạch đúng hoàn toàn {tally['all']}/{n}; " +
          ", ".join(f"{f} {tally[f]}/{n}" for f in FIELDS) + f"; chi phí {usd:.4f} USD")


class EvalDeps:
    """Phụ thuộc cho phép đo viết: kế hoạch đúng lấy từ đáp án (để hai nhà cung cấp viết trên cùng bảng số), không đọc
    thêm BCTC, không ghi CSDL."""

    def __init__(self, conn, client, gold: dict):
        from services.analyst.report import RealDeps
        self.real = RealDeps.__new__(RealDeps)      # bỏ qua __init__ (đọc người dùng của báo cáo trong CSDL)
        self.real.conn, self.real.client, self.real.report_id = conn, client, 0
        self.real.user, self.real._served = None, set()
        self.gold, self.saved = gold, {}

    def understand(self, question):
        from services.analyst import store
        from services.analyst.plan import Plan, check_plan
        e = self.gold["expect"]
        plan = Plan(e["kind"], e["tickers"], e["year"], e["period"], e["basis"], [], [], e["advice_request"])
        known = self.real.known_tickers()
        return check_plan(plan, known, lambda t: False, lambda ts: store.latest(self.real.conn, ts),
                          year_now=TODAY.year)

    def missing(self, plan):
        return []

    def request_reading(self, report_id, items):
        return []

    def build_sheet(self, plan):
        return self.real.build_sheet(plan)

    def reuse(self, report_id, plan, sources):
        return False

    def extra(self, plan, sheet, need):
        self.real.extra(plan, sheet, need)

    def write(self, *a):
        return self.real.write(*a)

    def known_tickers(self):
        return self.real.known_tickers()

    def save(self, report_id, **fields):
        self.saved.update(fields)


def cmd_write(args) -> None:
    from langgraph.checkpoint.memory import InMemorySaver
    from services.analyst.graph import build
    from services.db import connect
    rows = [g for g in load_golden(args.limit) if g["expect"]["tickers"] and "mã ngoài danh sách" not in g["tags"]
            and "mã không tồn tại" not in g["tags"] and "kỳ ngoài kho" not in g["tags"]]
    client = None
    with connect() as conn:
        for g in rows:
            cache = out_dir(args.provider) / f"{g['id']}_write.json"
            if cache.exists():
                continue
            client = client or client_for(args.provider)
            before, started = client.usage.usd, time.monotonic()
            deps = EvalDeps(conn, client, g)
            app = build(deps, InMemorySaver())
            try:
                app.invoke({"report_id": 0, "question": g["q"]}, {"configurable": {"thread_id": str(g["id"])},
                                                                  "recursion_limit": 60})
                saved = deps.saved
            except Exception as e:
                saved = {"status": "failed", "error": repr(e)[:500]}
            saved |= {"_usd": client.usage.usd - before, "_seconds": time.monotonic() - started}
            cache.write_text(json.dumps(saved, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            print(f"  [{g['id']}] {saved.get('status')} {saved['_usd']:.4f} USD")
    summary_write(args.provider)


def summary_write(provider: str) -> None:
    files = sorted(out_dir(provider).glob("*_write.json"))
    if not files:
        return
    first, final, kinds = Counter(), Counter(), Counter()
    usd, secs, done, dropped, rewrites = 0.0, 0.0, 0, 0, 0
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        usd, secs = usd + d.get("_usd", 0), secs + d.get("_seconds", 0)
        log = d.get("guard_log")
        if log:         # báo cáo hỏng vì không còn câu nào qua kiểm tra vẫn có nhật ký: vẫn tính lỗi của nó
            attempts = log["attempts"]
            first["sentences"] += attempts[0]["sentences"]
            first["bad"] += len({(v["section"], v["sentence"]) for v in attempts[0]["violations"]})
            for v in attempts[0]["violations"]:
                kinds[v["kind"]] += 1
            rewrites += len(attempts) - 1
            dropped += len(log["dropped"])
        if d.get("status") == "done":
            done += 1
            final["sentences"] += sum(len(s["sentences"]) for s in d["result"]["draft"]["sections"])
    n = len(files)
    print(f"{provider}: {done}/{n} báo cáo xong không cần người; lần viết đầu {first['bad']}/{first['sentences']} câu có lỗi "
          f"({dict(kinds)}); viết lại {rewrites} lần; bỏ {dropped} câu; còn {final['sentences']} câu; "
          f"trung bình {usd / n:.4f} USD và {secs / n:.0f} giây mỗi báo cáo")


def cmd_inject(args) -> None:
    from services.analyst.guard import check_sentence
    from services.analyst.sheet import FactSheet
    known = {"TCB", "VCB", "VPB", "MBB", "ACB", "BID", "CTG", "HDB", "LPB", "SHB", "SSB", "STB", "VIB", "FPT", "HPG",
             "MWG", "MSN", "MCH", "VNM", "SAB", "VIC", "VHM", "VRE", "VPL", "VJC", "GAS", "GVR", "BSR", "SSI", "TCX"}
    caught, tried = Counter(), Counter()
    for f in sorted(Path(out_dir("anthropic").parent).glob("*/*_write.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("status") != "done":
            continue
        sheet = FactSheet.from_json(d["sheet"])
        allowed = set(d["plan"]["tickers"])
        for sec in d["result"]["draft"]["sections"]:
            for s in sec["sentences"]:
                for kind, bad in mutations(s["text"]):
                    if kind == "foreign_ticker" and "HPG" in allowed | set(" ".join(x.text for x in sheet.facts).split()):
                        continue
                    tried[kind] += 1
                    r = check_sentence(bad, s["uses"], sheet, allowed, known)
                    caught[kind] += bool(r.violations)
    for kind in tried:
        print(f"  {kind}: bắt {caught[kind]}/{tried[kind]} ({caught[kind] / tried[kind] * 100:.1f}%)")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "write"):
        p = sub.add_parser(name)
        p.add_argument("--provider", required=True)
        p.add_argument("--limit", type=int)
    sub.add_parser("inject")
    sub.add_parser("summary")
    args = ap.parse_args()
    if args.cmd == "plan":
        cmd_plan(args)
    elif args.cmd == "write":
        cmd_write(args)
    elif args.cmd == "inject":
        cmd_inject(args)
    else:
        for d in sorted(out_dir("anthropic").parent.iterdir()):
            summary_write(d.name)


if __name__ == "__main__":
    main()
