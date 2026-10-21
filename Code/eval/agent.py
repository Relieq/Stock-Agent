"""Đo agent báo cáo (Baocao/dinh-huong/agent-bao-cao.md mục 11) trên bộ câu eval/data/agent_requests.jsonl.

    python eval/agent.py plan --provider anthropic [--limit 5]   # hiểu yêu cầu: so kế hoạch với đáp án
    python eval/agent.py write --provider anthropic [--limit 5]  # viết + kiểm số theo kế hoạch đúng (không đọc thêm BCTC)
    python eval/agent.py inject                                  # cấy lỗi vào câu đã đạt, đo bộ kiểm tra bắt được bao nhiêu
    python eval/agent.py summary                                 # in lại kết quả đã lưu, không gọi mô hình

Kết quả gọi mô hình lưu ở Data/raw/agent_eval/<nhà cung cấp>/: chạy lại chỉ chấm lại. Ngày cố định 21/10/2026 để các câu
"năm nay", "quý vừa rồi" có cùng đáp án ở mọi lần đo. Hai nhà cung cấp chạy cùng bộ câu, cùng bảng số.

Công bằng giữa hai nhà: bản đọc công văn giải trình lưu riêng theo nhà (<nhà>/explanations/), chi phí đọc công văn tách khỏi
chi phí viết; lỗi tạm thời (mạng, hết hạn mức) không được lưu nên lần chạy sau thử lại; mỗi bản lưu ghi mã mô hình đã trả
lời, kho còn thiếu số hay không, và bảng số gốc (trước khi mô hình xin thêm) để so hai nhà trên cùng dữ liệu. Bản lưu
cũ (không có `_fmt`) được chấm nhưng ghi "chưa rõ" ở các mục mới, và `write`/`plan` sẽ chạy lại chúng.
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
FMT = 2             # phiên bản định dạng bản lưu viết; bản cũ hơn thiếu các mục theo dõi công bằng
EXPLANATION_STEP = "explanation_read"


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


def mutations(text: str, foreign: str = "HPG") -> list[tuple[str, str]]:
    """Các cách làm sai một câu đã đạt: đổi số (lệch 10%), đảo tăng/giảm, đảo so sánh, đảo cao nhất/thấp nhất, chèn câu
    khuyến nghị, chèn mã lạ (`foreign`). Chỉ giữ cách làm câu đổi thật; "tăng trưởng" không đảo (thành "giảm trưởng" không
    còn là câu tiếng Việt)."""
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
            pat = rf"\b{a}\b(?!\s+trưởng)"
            if re.search(pat, text):
                out.append((kind, re.sub(pat, b, text, count=1)))
                break
    out.append(("advice", text.rstrip(".") + "; nhà đầu tư nên mua cổ phiếu này."))
    out.append(("foreign_ticker", text.rstrip(".") + f", tốt hơn {foreign}."))
    return [(k, t) for k, t in out if t != text]


def client_for(provider: str):
    from services.llm import VisionClient, _provider_config, configured
    model = dict(configured()).get(provider)
    return VisionClient(_provider_config(provider, model))


def eval_root() -> Path:
    from services.ingestion.registry import raw_data_dir
    return raw_data_dir() / "agent_eval"


def out_dir(provider: str, create: bool = False) -> Path:
    d = eval_root() / provider
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def provider_dirs() -> list[str]:
    root = eval_root()
    return sorted(d.name for d in root.iterdir() if d.is_dir()) if root.is_dir() else []


def load_caches(provider: str, kind: str) -> dict[str, dict]:
    """Các bản lưu `<id>_<kind>.json` của một nhà, khóa là id câu (chuỗi). Không tạo thư mục."""
    d = out_dir(provider)
    if not d.is_dir():
        return {}
    return {f.name.split("_")[0]: json.loads(f.read_text(encoding="utf-8"))
            for f in sorted(d.glob(f"*_{kind}.json"), key=lambda f: int(f.name.split("_")[0]))}


def steps_delta(before: dict, after: dict) -> dict:
    """Chi phí và thời gian phát sinh theo từng bước giữa hai lần chụp `client.steps_snapshot()`."""
    out = {}
    for step, a in after.items():
        b = before.get(step, {})
        usd, secs = a.get("usd", 0.0) - b.get("usd", 0.0), a.get("seconds", 0.0) - b.get("seconds", 0.0)
        if usd or secs or a.get("calls", 0) != b.get("calls", 0):
            out[step] = {"usd": usd, "seconds": secs}
    return out


def cmd_plan(args) -> None:
    from services.analyst.plan import parse_request
    from services.db import connect
    client = None
    with connect() as conn:
        companies = conn.execute("SELECT ticker, name FROM companies WHERE tracked ORDER BY ticker").fetchall()
    tally, usd = Counter(), 0.0
    rows = load_golden(args.limit)
    for g in rows:
        cache = out_dir(args.provider, create=True) / f"{g['id']}_plan.json"
        got = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None
        if got is None or "_model" not in got:      # chưa có, hoặc bản cũ chưa ghi mã mô hình: chạy (lại)
            client = client or client_for(args.provider)
            before = client.usage.usd
            got = parse_request(client, g["q"], TODAY, companies).to_json() | {
                "_usd": client.usage.usd - before, "_provider": client.cfg.provider, "_model": client.cfg.model}
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
    thêm BCTC, không ghi CSDL. Ghi lại để đối chiếu giữa hai nhà: kho còn thiếu số của kế hoạch đã kiểm (`store_missing`)
    và bảng số gốc trước khi mô hình xin thêm (`base_facts`). `letter_dir`: nơi lưu bản đọc công văn của riêng nhà này."""

    def __init__(self, conn, client, gold: dict, letter_dir: Path | None = None):
        from services.analyst.report import RealDeps
        self.real = RealDeps.__new__(RealDeps)      # bỏ qua __init__ (đọc người dùng của báo cáo trong CSDL)
        self.real.conn, self.real.client, self.real.report_id = conn, client, 0
        self.real.user, self.real._served = None, set()
        self.real.letter_cache_dir = letter_dir
        self.gold, self.saved = gold, {}
        self.store_missing: list[dict] | None = None
        self.base_facts: list[str] | None = None

    def understand(self, question):
        from services.analyst import store
        from services.analyst.plan import Plan, check_plan
        e = self.gold["expect"]
        plan = Plan(e["kind"], e["tickers"], e["year"], e["period"], e["basis"], [], [], e["advice_request"])
        known = self.real.known_tickers()
        return check_plan(plan, known, lambda t: False, lambda ts: store.latest(self.real.conn, ts),
                          year_now=TODAY.year)

    def missing(self, plan):
        from services.analyst import store
        self.store_missing = [{k: m[k] for k in ("ticker", "year", "period")} for m in store.missing(self.real.conn, plan)]
        return []

    def request_reading(self, report_id, items):
        return []

    def build_sheet(self, plan):
        out = self.real.build_sheet(plan)
        self.base_facts = [f.text for f in out[0].facts]
        return out

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
            cache = out_dir(args.provider, create=True) / f"{g['id']}_write.json"
            if cache.exists() and json.loads(cache.read_text(encoding="utf-8")).get("_fmt") == FMT:
                continue
            client = client or client_for(args.provider)
            before, steps_before, started = client.usage.usd, client.steps_snapshot(), time.monotonic()
            deps = EvalDeps(conn, client, g, letter_dir=out_dir(args.provider) / "explanations")
            app = build(deps, InMemorySaver())
            try:
                app.invoke({"report_id": 0, "question": g["q"]}, {"configurable": {"thread_id": str(g["id"])},
                                                                  "recursion_limit": 60})
            except Exception as e:      # lỗi tạm thời (mạng, hết hạn mức) không phải kết quả của agent: không lưu, lần sau thử lại
                print(f"  [{g['id']}] lỗi, không lưu: {repr(e)[:300]} ({client.usage.usd - before:.4f} USD đã tốn)")
                continue
            if "status" not in deps.saved:
                print(f"  [{g['id']}] đồ thị dừng không có kết quả, không lưu")
                continue
            saved = deps.saved | {
                "_fmt": FMT, "_provider": client.cfg.provider, "_model": client.cfg.model,
                "_usd": client.usage.usd - before, "_seconds": time.monotonic() - started,
                "_steps": steps_delta(steps_before, client.steps_snapshot()),
                "store_missing": deps.store_missing, "base_facts": deps.base_facts}
            cache.write_text(json.dumps(saved, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            print(f"  [{g['id']}] {saved.get('status')} {saved['_usd']:.4f} USD")
    summary_write(args.provider)


def provider_stats(caches: dict[str, dict], plans: dict[str, dict] | None = None) -> dict:
    """Số liệu gộp của một nhà từ các bản lưu viết (thuần, để test). Bản lưu cũ (không `_fmt`) tính vào `legacy`."""
    st = Counter()
    kinds = Counter()
    models, usd_expl, usd_write, secs_write = set(), 0.0, 0.0, 0.0
    for d in caches.values():
        st["n"] += 1
        new = d.get("_fmt") == FMT
        models.add(f"{d['_provider']}/{d['_model']}" if new else "chưa ghi")
        if new:
            steps = d.get("_steps", {})
            e = steps.get(EXPLANATION_STEP, {})
            st["costed"] += 1
            usd_expl += e.get("usd", 0.0)
            usd_write += d.get("_usd", 0.0) - e.get("usd", 0.0)
            secs_write += d.get("_seconds", 0.0) - e.get("seconds", 0.0)
        else:
            st["legacy"] += 1
            st["legacy_usd"] += d.get("_usd", 0.0)
        log = d.get("guard_log")
        if log:         # báo cáo hỏng vì không còn câu nào qua kiểm tra vẫn có nhật ký: vẫn tính lỗi của nó
            attempts = log["attempts"]
            st["sentences"] += attempts[0]["sentences"]
            st["bad"] += len({(v["section"], v["sentence"]) for v in attempts[0]["violations"]})
            for v in attempts[0]["violations"]:
                kinds[v["kind"]] += 1
            st["rewrites"] += len(attempts) - 1
            st["dropped"] += len(log["dropped"])
        if d.get("status") == "done":
            st["final"] += sum(len(s["sentences"]) for s in d["result"]["draft"]["sections"])
            if not new:
                st["done_unknown"] += 1
            elif d.get("store_missing"):
                st["done_thin"] += 1
            else:
                st["done_full"] += 1
        else:
            st["not_done"] += 1
    plans = plans or {}
    return {"st": st, "kinds": dict(kinds), "models": sorted(models), "usd_write": usd_write, "usd_expl": usd_expl,
            "secs_write": secs_write, "plan_usd": sum(p.get("_usd", 0.0) for p in plans.values()),
            "plan_n": len(plans), "plan_models": sorted({f"{p['_provider']}/{p['_model']}" for p in plans.values()
                                                         if "_model" in p})}


def format_stats(provider: str, s: dict) -> list[str]:
    st, c = s["st"], s["st"]["costed"]
    out = [f"{provider} [{', '.join(s['models'])}]: {st['n']} báo cáo; xong đủ số {st['done_full']}; "
           f"xong nhưng thiếu số (kho chưa có BCTC của kế hoạch) {st['done_thin']}; xong, chưa rõ kho đủ số không "
           f"{st['done_unknown']}; không xong {st['not_done']}",
           f"  lần viết đầu: {st['bad']}/{st['sentences']} câu có lỗi (đếm theo câu); lỗi theo loại, đếm theo lỗi: {s['kinds']}; "
           f"viết lại {st['rewrites']} lần; bỏ {st['dropped']} câu; còn {st['final']} câu"]
    if c:
        out.append(f"  chi phí viết {s['usd_write'] / c:.4f} USD và {s['secs_write'] / c:.0f} giây mỗi báo cáo (không gồm đọc công văn, "
                   f"tính trên {c} báo cáo); đọc công văn giải trình {s['usd_expl']:.4f} USD tổng (tính riêng, mỗi nhà đọc bản của mình)")
    if st["legacy"]:
        out.append(f"  {st['legacy']} báo cáo là bản lưu cũ chưa tách chi phí đọc công văn ({st['legacy_usd']:.4f} USD gồm cả đọc "
                   f"công văn dùng chung): chưa so được chi phí, sẽ chạy lại ở lần `write` tới")
    if s["plan_n"]:
        out.append(f"  hiểu yêu cầu (kế hoạch): {s['plan_usd']:.4f} USD cho {s['plan_n']} câu "
                   f"[{', '.join(s['plan_models']) or 'chưa ghi mã mô hình'}]")
    return out


def compare_providers(by_provider: dict[str, dict[str, dict]]) -> dict:
    """So từng câu giữa nhà đầu tiên (theo tên) và các nhà còn lại: kế hoạch đã kiểm và bảng số gốc phải giống nhau thì
    hai nhà mới viết trên cùng dữ liệu. Bản lưu cũ không có bảng số gốc: đếm vào `unknown`."""
    names = sorted(by_provider)
    res = {"compared": 0, "same": 0, "unknown": 0, "plan_diff": [], "sheet_diff": []}
    for other in names[1:]:
        a_all, b_all = by_provider[names[0]], by_provider[other]
        for qid in sorted(set(a_all) & set(b_all), key=int):
            a, b = a_all[qid], b_all[qid]
            res["compared"] += 1
            pa, pb = _norm_plan(a.get("plan")), _norm_plan(b.get("plan"))
            if pa != pb:
                res["plan_diff"].append(f"[{qid}] kế hoạch đã kiểm khác: {names[0]} {pa} / {other} {pb}")
                continue
            fa, fb = a.get("base_facts"), b.get("base_facts")
            if fa is None or fb is None:
                res["unknown"] += 1
            elif fa != fb:
                first = next((i for i, (x, y) in enumerate(zip(fa, fb)) if x != y), min(len(fa), len(fb)))
                res["sheet_diff"].append(f"[{qid}] bảng số gốc khác: {names[0]} {len(fa)} dòng / {other} {len(fb)} dòng; "
                                         f"khác từ dòng {first + 1}")
            else:
                res["same"] += 1
    return res


def _norm_plan(plan: dict | None) -> str:
    p = dict(plan or {})
    if isinstance(p.get("tickers"), list):
        p["tickers"] = sorted(p["tickers"])
    return json.dumps(p, sort_keys=True, ensure_ascii=False)


def format_comparison(res: dict) -> list[str]:
    out = [f"so hai nhà trên cùng câu: {res['compared']} cặp; cùng kế hoạch và cùng bảng số gốc {res['same']}; "
           f"lệch kế hoạch {len(res['plan_diff'])}; lệch bảng số gốc {len(res['sheet_diff'])}; "
           f"chưa rõ bảng số gốc (bản lưu cũ) {res['unknown']}"]
    out += ["  " + x for x in res["plan_diff"] + res["sheet_diff"]]
    return out


def summary_write(provider: str) -> None:
    caches = load_caches(provider, "write")
    if caches:
        for line in format_stats(provider, provider_stats(caches, load_caches(provider, "plan"))):
            print(line)


def cmd_summary(args) -> None:
    provs = provider_dirs()
    for p in provs:
        summary_write(p)
    by = {p: load_caches(p, "write") for p in provs}
    by = {p: c for p, c in by.items() if c}
    if len(by) > 1:
        for line in format_comparison(compare_providers(by)):
            print(line)


def known_tickers(docs: list[dict], golden: list[dict]) -> set[str]:
    """Mã mà bộ kiểm tra coi là mã thật: mã trong kế hoạch đã lưu, mã gắn với dòng trong bảng số, mã trong bộ câu (trừ mã
    không tồn tại)."""
    known = set()
    for d in docs:
        known |= set((d.get("plan") or {}).get("tickers", []))
        known |= {f["ticker"] for f in d.get("sheet", []) if f.get("ticker")}
    for g in golden:
        if "mã không tồn tại" not in g["tags"]:
            known |= set(g["expect"]["tickers"])
    return known


def cmd_inject(args) -> None:
    from services.analyst.guard import check_sentence
    from services.analyst.sheet import FactSheet
    docs = [d for p in provider_dirs() for d in load_caches(p, "write").values() if d.get("status") == "done"]
    known = known_tickers(docs, load_golden())
    caught, tried = Counter(), Counter()
    for d in docs:
        sheet = FactSheet.from_json(d["sheet"])
        allowed = set(d["plan"]["tickers"])
        sheet_text = " ".join(f.text for f in sheet.facts)
        foreign = next((t for t in ["HPG"] + sorted(known) if t in known and t not in allowed and t not in sheet_text), None)
        for sec in d["result"]["draft"]["sections"]:
            for s in sec["sentences"]:
                for kind, bad in mutations(s["text"], foreign or "HPG"):
                    if kind == "foreign_ticker" and foreign is None:
                        continue
                    tried[kind] += 1
                    r = check_sentence(bad, s["uses"], sheet, allowed, known)
                    caught[kind] += bool(r.violations)
    print(f"cấy lỗi vào câu đã đạt ({len(docs)} báo cáo xong, mã lạ lấy từ {len(known)} mã đã biết); số lần cấy, mỗi câu mỗi kiểu một lần:")
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
    {"plan": cmd_plan, "write": cmd_write, "inject": cmd_inject, "summary": cmd_summary}[args.cmd](args)


if __name__ == "__main__":
    main()
