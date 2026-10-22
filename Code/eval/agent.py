"""Đo agent báo cáo (Baocao/dinh-huong/agent-bao-cao.md mục 11) trên bộ câu eval/data/agent_requests.jsonl.

    python eval/agent.py plan --provider anthropic [--limit 5]   # hiểu yêu cầu: so kế hoạch với đáp án
    python eval/agent.py write --provider anthropic [--limit 5]  # viết + kiểm số theo kế hoạch đúng (không đọc thêm BCTC)
    python eval/agent.py inject                                  # cấy lỗi vào câu đã đạt, đo bộ kiểm tra bắt được bao nhiêu
    python eval/agent.py summary                                 # in lại kết quả đã lưu, không gọi mô hình

Kết quả gọi mô hình lưu ở Data/raw/agent_eval/<nhà cung cấp>/: chạy lại chỉ chấm lại. Ngày cố định 21/10/2026 để các câu
"năm nay", "quý vừa rồi" có cùng đáp án ở mọi lần đo. Hai nhà cung cấp chạy cùng bộ câu, cùng bảng số.

Công bằng giữa hai nhà: bản đọc công văn giải trình lưu riêng theo nhà (<nhà>/explanations/), chi phí đọc công văn tách khỏi
chi phí viết; lỗi mạng/máy chủ thử lại tối đa 2 lần, còn lỗi tất định (bị cắt, từ chối, JSON sai...) hoặc lỗi mạng vẫn
không qua được lưu thành báo cáo không xong (không bỏ khỏi mẫu số); mỗi bản lưu ghi mã mô hình đã trả
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
SCREEN_FIELDS = ("sector", "measure")      # chỉ chấm với câu "mã nào tốt nhất" (loại screen)
FMT = 2             # phiên bản định dạng bản lưu viết; bản cũ hơn thiếu các mục theo dõi công bằng
EXPLANATION_STEP = "explanation_read"


def load_golden(limit: int | None = None) -> list[dict]:
    rows = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows[:limit] if limit else rows


def write_case(g: dict) -> dict:
    """Câu và kế hoạch dùng cho phép đo viết: câu có `write_as` (kỳ gốc chưa có BCTC trong kho, ví dụ quý 3 khi công ty
    chưa công bố) được đo trên bản dời sang kỳ đã có số; phép đo hiểu yêu cầu vẫn dùng câu gốc."""
    w = g.get("write_as")
    return {"q": w["q"], "expect": g["expect"] | w["expect"]} if w else {"q": g["q"], "expect": g["expect"]}


def score_plan(got: dict, expect: dict) -> dict[str, bool]:
    out = {}
    for f in FIELDS + (SCREEN_FIELDS if expect["kind"] == "screen" else ()):
        if f == "tickers":
            out[f] = sorted(t.strip().upper() for t in got.get(f, [])) == sorted(expect[f])
        else:
            out[f] = got.get(f) == expect[f]
    return out


def real_tickers(golden: list[dict], tracked: set[str]) -> set[str]:
    """Mã có thật: mã đang theo dõi và mã trong đáp án của bộ câu (trừ câu "mã không tồn tại")."""
    return tracked | {t for g in golden if "mã không tồn tại" not in g["tags"] for t in g["expect"]["tickers"]}


def outcome(plan: dict, real: set[str]) -> dict:
    """Việc hệ thống thực sự làm sau khi code kiểm kế hoạch (plan.check_plan): không có mã (trừ câu "mã nào tốt nhất")
    hoặc có mã không tồn tại thì hỏi lại; câu "mã nào tốt nhất" có nêu mã thì thành vị trí trong nhóm hoặc so các mã;
    một mã thì không thể "so nhiều mã"; bán niên/cả năm luôn lũy kế, quý 1 luôn riêng quý."""
    tickers = sorted({t.strip().upper() for t in plan.get("tickers", []) if t.strip()})
    kind = plan["kind"]
    if kind == "screen" and tickers:
        kind = "rank" if len(tickers) == 1 else "compare"
    if (not tickers and kind != "screen") or any(t not in real for t in tickers):
        return {"ask": True}
    if kind in ("compare", "yoy"):
        kind = "compare" if len(tickers) > 1 else "yoy"
    basis = "ytd" if plan["period"] in ("H1", "FY") else "quarter" if plan["period"] == "Q1" else plan["basis"]
    out = {"ask": False, "kind": kind, "tickers": tickers, "year": plan["year"], "period": plan["period"],
           "basis": basis, "advice_request": plan["advice_request"]}
    if kind == "screen":
        out |= {"sector": plan.get("sector", "all"), "measure": plan.get("measure", "growth")}
    return out


def mutations(text: str, foreign: str = "HPG") -> list[tuple[str, str]]:
    """Các cách làm sai một câu đã đạt: đổi số (lệch 10%), đảo tăng/giảm, đảo so sánh, đảo cao nhất/thấp nhất, đảo lãi/lỗ,
    đổi thứ hạng (thứ N thành N+1), chèn câu khuyến nghị, chèn mã lạ (`foreign`). Chỉ giữ cách làm câu đổi thật; "tăng
    trưởng" không đảo (thành "giảm trưởng" không còn là câu tiếng Việt)."""
    from services.analyst.guard import numbers, ranks
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
            # "tăng hay giảm", "giảm hoặc tăng" không khẳng định chiều nào: đổi chữ ở đó không làm câu sai
            pat = (rf"(?<!tăng hay )(?<!giảm hay )(?<!tăng hoặc )(?<!giảm hoặc )\b{a}\b(?!\s+trưởng)"
                   rf"(?!\s+(?:hay|hoặc)\s+(?:tăng|giảm)\b)")
            if re.search(pat, text):
                out.append((kind, re.sub(pat, b, text, count=1)))
                break
    # đảo lãi/lỗ: chữ đứng riêng, không phải "lãi/lỗ" (tên khoản mục), "thu nhập/chi phí lãi", "lãi suất/vay"
    m = re.search(r"(?i)(?<![/\w])(?<!thu nhập )(?<!chi phí )(lãi|lỗ)(?![/\w])(?!\s+(?:suất|vay)\b)", text)
    if m:
        w = "lỗ" if m.group(1).lower() == "lãi" else "lãi"
        out.append(("profit_loss", text[:m.start()] + (w.capitalize() if m.group(1)[0].isupper() else w)
                    + text[m.end():]))
    rs = ranks(text)
    if rs:          # đổi thứ hạng: thứ N thành N+1
        r = rs[0]
        out.append(("rank", text[:r.start("n")] + str(int(r.group("n")) + 1) + text[r.end("n"):]))
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
    real = real_tickers(load_golden(), {t for t, _ in companies})
    for g in rows:
        cache = out_dir(args.provider, create=True) / f"{g['id']}_plan.json"
        got = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else None
        if got is None or "_model" not in got:      # chưa có, hoặc bản cũ chưa ghi mã mô hình: chạy (lại)
            client = client or client_for(args.provider)
            before = client.usage.usd
            try:
                got = parse_request(client, g["q"], TODAY, companies).to_json() | {
                    "_usd": client.usage.usd - before, "_provider": client.cfg.provider, "_model": client.cfg.model}
            except Exception as e:
                if is_account_problem(e):
                    stop_for_account(args.provider, e, client.usage.usd - before)
                    raise SystemExit(1)
                raise
            cache.write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
        usd += got.get("_usd", 0.0)
        s = score_plan(got, g["expect"])
        tally["all"] += all(s.values())
        for f, ok in s.items():
            tally[f] += ok
        same = outcome(got, real) == outcome(g["expect"], real)
        tally["outcome"] += same
        if not same:
            print(f"  [{g['id']}] {g['q']}: hệ thống làm khác đáp án (trường lệch {[f for f, ok in s.items() if not ok]})"
                  f" -> {got}")
    n = len(rows)
    screen = [g for g in rows if g["expect"]["kind"] == "screen"]
    ok_screen = sum(outcome(json.loads((out_dir(args.provider) / f"{g['id']}_plan.json").read_text(encoding="utf-8")),
                            real) == outcome(g["expect"], real) for g in screen)
    print(f"{args.provider}: hệ thống làm đúng yêu cầu {tally['outcome']}/{n} câu (sau khi code kiểm kế hoạch; riêng câu "
          f"\"mã nào tốt nhất\" {ok_screen}/{len(screen)}); kế hoạch thô của mô hình đúng hoàn toàn {tally['all']}/{n}; " +
          ", ".join(f"{f} {tally[f]}/{n}" for f in FIELDS) +
          "".join(f", {f} {tally[f]}/{len(screen)}" for f in SCREEN_FIELDS) + f"; chi phí {usd:.4f} USD")


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
        e = write_case(self.gold)["expect"]
        plan = Plan(e["kind"], e["tickers"], e["year"], e["period"], e["basis"], [], [], e["advice_request"],
                    e.get("sector", "all"), e.get("measure", "growth"))
        known = self.real.known_tickers()
        return check_plan(plan, known, lambda t: False, lambda ts: store.latest(self.real.conn, ts),
                          year_now=TODAY.year, latest_all=lambda sector: store.latest_all(self.real.conn, sector))

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


MAX_RETRIES = 2


def stop_for_account(provider: str, e: Exception, usd: float) -> None:
    print(f"Tài khoản {provider} hết tiền/hạn mức: dừng đo, nạp tiền rồi chạy lại (câu đang chạy không được lưu, "
          f"đã tốn {usd:.4f} USD; các câu đã lưu giữ nguyên). Lỗi: {repr(e)[:300]}", file=sys.stderr)


ACCOUNT_WORDS = ("quota", "credit", "billing")


def is_account_problem(e: Exception) -> bool:
    """Tài khoản hết tiền/hạn mức (OpenAI insufficient_quota = 429, Anthropic credit_balance = 400, mọi 402, hoặc thông báo
    nhắc quota/credit/billing). Đây không phải lỗi của mô hình: phải dừng đo, không ghi vào kết quả. Kiểm trước
    `is_transient` để 429 hết hạn mức không bị thử lại."""
    status = getattr(e, "status_code", None)
    if status == 402:
        return True
    if status in (400, 429, None):
        text = str(e).lower()
        return any(w in text for w in ACCOUNT_WORDS) and (status is not None or type(e).__name__ == "ProviderUnavailable")
    return False


def is_transient(e: Exception) -> bool:
    """Lỗi tạm thời đáng thử lại: mất kết nối, quá thời gian, 408/429, lỗi máy chủ 5xx, hoặc nhà cung cấp báo không trả
    lời được (ProviderUnavailable sticky). Sai khóa/hết tiền (401-403), bị cắt do quá dài, từ chối, JSON sai, lỗi đệ quy
    của đồ thị: thử lại cũng ra như cũ nên không phải lỗi tạm thời. Hết tiền/hạn mức (`is_account_problem`) loại trước."""
    from services.llm import ProviderUnavailable
    if is_account_problem(e):
        return False
    if isinstance(e, ProviderUnavailable):
        return e.sticky
    status = getattr(e, "status_code", None)
    if status is None:
        return type(e).__name__ in ("APIConnectionError", "APITimeoutError")
    return status in (408, 429) or status >= 500


def with_retries(fn, retries: int = MAX_RETRIES, pause: float = 5.0, sleep=time.sleep):
    """Chạy `fn`; lỗi tạm thời thử lại tối đa `retries` lần. Trả (kết quả, None) hoặc (None, (loại lỗi, ngoại lệ)) với loại
    "deterministic", "transient_exhausted" hoặc "account" (hết tiền/hạn mức: người gọi phải dừng đo, không ghi kết quả).
    Lỗi không được bỏ khỏi mẫu số: báo cáo hỏng vẫn được ghi là không xong."""
    for n in range(retries + 1):
        try:
            return fn(), None
        except Exception as e:
            if is_account_problem(e):
                return None, ("account", e)
            if not is_transient(e):
                return None, ("deterministic", e)
            if n == retries:
                return None, ("transient_exhausted", e)
            sleep(pause * (n + 1))


def eligible(rows: list[dict]) -> list[dict]:
    """Câu mà phép đo viết chạy được: có mã (hoặc câu "mã nào tốt nhất"), mã trong danh sách và tồn tại, kỳ có trong
    kho."""
    return [g for g in rows if (g["expect"]["tickers"] or g["expect"].get("kind") == "screen")
            and "mã ngoài danh sách" not in g["tags"]
            and "mã không tồn tại" not in g["tags"] and "kỳ ngoài kho" not in g["tags"]]


def cmd_write(args) -> None:
    from langgraph.checkpoint.memory import InMemorySaver
    from services.analyst.graph import build
    from services.db import connect
    rows = eligible(load_golden(args.limit))
    client = None
    with connect() as conn:
        for g in rows:
            cache = out_dir(args.provider, create=True) / f"{g['id']}_write.json"
            if cache.exists() and json.loads(cache.read_text(encoding="utf-8")).get("_fmt") == FMT:
                continue
            client = client or client_for(args.provider)
            before, steps_before, started = client.usage.usd, client.steps_snapshot(), time.monotonic()
            holder = {}

            def run():
                try:
                    conn.rollback()     # lần thử trước có thể để giao dịch dở
                except Exception:
                    pass
                deps = holder["deps"] = EvalDeps(conn, client, g, letter_dir=out_dir(args.provider) / "explanations")
                build(deps, InMemorySaver()).invoke(
                    {"report_id": 0, "question": write_case(g)["q"]},
                    {"configurable": {"thread_id": str(g["id"])}, "recursion_limit": 60})
                return deps

            _, failure = with_retries(run)
            if failure and failure[0] == "account":     # không phải lỗi của mô hình: không lưu, dừng cả lần đo
                stop_for_account(args.provider, failure[1], client.usage.usd - before)
                summary_write(args.provider)
                raise SystemExit(1)
            deps = holder.get("deps") or EvalDeps(conn, client, g)      # dựng được thì có kế hoạch/bảng số đã ghi
            saved = dict(deps.saved)
            if failure:     # lỗi tất định (bị cắt, từ chối, JSON sai...) hoặc lỗi mạng vẫn không qua sau khi thử lại: tính là báo cáo không xong
                kind, e = failure
                saved |= {"status": "failed", "error": repr(e)[:500], "_error_kind": kind}
            saved |= {
                "_fmt": FMT, "_provider": client.cfg.provider, "_model": client.cfg.model,
                "_usd": client.usage.usd - before, "_seconds": time.monotonic() - started,
                "_steps": steps_delta(steps_before, client.steps_snapshot()),
                "store_missing": deps.store_missing, "base_facts": deps.base_facts}
            cache.write_text(json.dumps(saved, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
            print(f"  [{g['id']}] {saved.get('status')}{' (' + saved['_error_kind'] + ')' if failure else ''} "
                  f"{saved['_usd']:.4f} USD")
    summary_write(args.provider)


def provider_stats(caches: dict[str, dict], plans: dict[str, dict] | None = None, eligible_n: int | None = None) -> dict:
    """Số liệu gộp của một nhà từ các bản lưu viết (thuần, để test). Bản lưu cũ (không `_fmt`) tính vào `legacy`.
    `eligible_n`: số câu phép đo viết phải chạy, để thấy câu nào chưa có kết quả."""
    st = Counter()
    kinds, errors = Counter(), Counter()
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
            if d.get("_error_kind"):
                errors[d["_error_kind"]] += 1
    plans = plans or {}
    return {"st": st, "kinds": dict(kinds), "errors": dict(errors), "eligible": eligible_n, "models": sorted(models), "usd_write": usd_write, "usd_expl": usd_expl,
            "secs_write": secs_write, "plan_usd": sum(p.get("_usd", 0.0) for p in plans.values()),
            "plan_n": len(plans), "plan_models": sorted({f"{p['_provider']}/{p['_model']}" for p in plans.values()
                                                         if "_model" in p})}


def format_stats(provider: str, s: dict) -> list[str]:
    st, c = s["st"], s["st"]["costed"]
    have = f"{st['n']}/{s['eligible']} câu đã có kết quả" if s["eligible"] is not None else f"{st['n']} câu đã có kết quả"
    errs = f" (lỗi: {s['errors']})" if s["errors"] else ""
    out = [f"{provider} [{', '.join(s['models'])}]: {have}; xong đủ số {st['done_full']}; "
           f"xong nhưng thiếu số (kho chưa có BCTC của kế hoạch) {st['done_thin']}; xong, chưa rõ kho đủ số không "
           f"{st['done_unknown']}; không xong {st['not_done']}{errs}",
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
        for line in format_stats(provider, provider_stats(caches, load_caches(provider, "plan"),
                                                           len(eligible(load_golden())))):
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
    clean, flagged = 0, 0           # câu gốc (đã đạt) có bị bộ kiểm tra hiện tại bắt nhầm không
    for d in docs:
        sheet = FactSheet.from_json(d["sheet"])
        allowed = set(d["plan"]["tickers"])
        sheet_text = " ".join(f.text for f in sheet.facts)
        foreign = next((t for t in ["HPG"] + sorted(known) if t in known and t not in allowed and t not in sheet_text), None)
        for sec in d["result"]["draft"]["sections"]:
            for s in sec["sentences"]:
                clean += 1
                flagged += bool(check_sentence(s["text"], s["uses"], sheet, allowed, known).violations)
                for kind, bad in mutations(s["text"], foreign or "HPG"):
                    if kind == "foreign_ticker" and foreign is None:
                        continue
                    tried[kind] += 1
                    r = check_sentence(bad, s["uses"], sheet, allowed, known)
                    caught[kind] += bool(r.violations)
    print(f"cấy lỗi vào câu đã đạt ({len(docs)} báo cáo xong, mã lạ lấy từ {len(known)} mã đã biết); số lần cấy, mỗi câu mỗi kiểu một lần:")
    for kind in tried:
        print(f"  {kind}: bắt {caught[kind]}/{tried[kind]} ({caught[kind] / tried[kind] * 100:.1f}%)")
    print(f"  câu gốc bị bắt nhầm: {flagged}/{clean}")


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
