"""So agent báo cáo với trợ lý AI đa năng có tìm web, trên cùng câu hỏi (báo cáo kỹ thuật, mục so với trợ lý đa năng).

    python eval/general.py run --provider anthropic --model claude-sonnet-5-5 [--ids 1,3]
    python eval/general.py run --provider openai --model gpt-5.4
    python eval/general.py score            # chấm lại câu trả lời đã lưu và báo cáo của agent, không gọi mô hình

Hai trợ lý cùng hạng giá của hai hãng, cùng bật tìm web, cùng lời dặn ngắn, cùng ngày cố định 21/10/2026. Câu trả lời lưu ở
Data/raw/agent_eval_general/<nhà>/<id>.json, chạy lại chỉ chấm lại.

Chấm bằng code: mỗi số tiền hoặc % trong câu trả lời được gắn với mã và chỉ tiêu nhắc gần nhất trước nó trong cùng câu (tên
công ty được đổi ra mã), rồi so với số đã kiểm chứng của mã đó: "đúng" (khớp kỳ được hỏi: kỳ này, cùng kỳ, mức hoặc %
thay đổi), "khác kỳ" (khớp số của kỳ khác hoặc cách tính khác: lũy kế thay vì riêng quý, quý trước), "sai" (kho có số của
chỉ tiêu đó mà không khớp), "không kiểm được" (không gắn được mã và chỉ tiêu trong danh mục, hoặc kho không có số). Cùng bộ
chấm chạy trên báo cáo của agent (lấy từ bản lưu của eval/agent.py write) để kiểm chính bộ chấm.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agent as agent_eval  # noqa: E402

IDS = [1, 13, 6, 9, 22, 7, 60, 61]      # đủ bốn loại câu hỏi và một câu xin khuyến nghị

PROMPT = ("Hôm nay là 21/10/2026. Trả lời câu hỏi sau bằng tiếng Việt, ngắn gọn, viết thành đoạn văn (không dùng bảng), "
          "nêu số liệu cụ thể nếu có.\n\nCâu hỏi: {q}")
SEARCH_USD = 0.01           # giá mỗi lần tìm web của cả hai hãng (10 USD / 1.000 lần)
CATS = ("đúng", "khác kỳ", "sai", "không kiểm được")


def root(provider: str | None = None, create: bool = False) -> Path:
    from services.ingestion.registry import raw_data_dir
    d = raw_data_dir() / "agent_eval_general" / (provider or "")
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def ask_anthropic(model: str, prompt: str) -> dict:
    import anthropic

    from services.llm import _provider_config
    client = anthropic.Anthropic(api_key=_provider_config("anthropic", model).api_key, max_retries=4, timeout=600)
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]
    messages = [{"role": "user", "content": prompt}]
    ti = to = searches = 0
    for _ in range(4):          # tìm web dài có thể dừng ở pause_turn: gửi lại để máy chủ chạy tiếp
        resp = client.messages.create(model=model, max_tokens=16_000, tools=tools, messages=messages)
        ti, to = ti + resp.usage.input_tokens, to + resp.usage.output_tokens
        stu = getattr(resp.usage, "server_tool_use", None)
        searches += getattr(stu, "web_search_requests", 0) or 0
        if resp.stop_reason != "pause_turn":
            break
        messages = [{"role": "user", "content": prompt}, {"role": "assistant", "content": resp.content}]
    text = "".join(b.text for b in resp.content if b.type == "text")
    return {"answer": text, "input_tokens": ti, "output_tokens": to, "searches": searches, "stop": resp.stop_reason}


def ask_openai(model: str, prompt: str) -> dict:
    from openai import OpenAI

    from services.llm import _provider_config
    client = OpenAI(api_key=_provider_config("openai", model).api_key, max_retries=4, timeout=600)
    resp = client.responses.create(model=model, tools=[{"type": "web_search"}], input=prompt)
    searches = sum(1 for o in resp.output if getattr(o, "type", "") == "web_search_call")
    return {"answer": resp.output_text, "input_tokens": resp.usage.input_tokens,
            "output_tokens": resp.usage.output_tokens, "searches": searches, "stop": resp.status}


def cmd_run(args) -> None:
    from services.llm import cost_usd
    ids = [int(x) for x in args.ids.split(",")] if args.ids else IDS
    gold = {g["id"]: g for g in agent_eval.load_golden()}
    ask = {"anthropic": ask_anthropic, "openai": ask_openai}[args.provider]
    total = 0.0
    for i in ids:
        cache = root(args.provider, create=True) / f"{i}.json"
        if cache.exists():
            continue
        q = agent_eval.write_case(gold[i])["q"]
        started = time.monotonic()
        got = ask(args.model, PROMPT.format(q=q))
        usd = (cost_usd(args.model, got["input_tokens"], got["output_tokens"]) or 0.0) + got["searches"] * SEARCH_USD
        got |= {"id": i, "q": q, "model": args.model, "usd": usd, "seconds": time.monotonic() - started}
        cache.write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
        total += usd
        print(f"  [{i}] {got['searches']} lần tìm, {usd:.4f} USD, {got['seconds']:.0f} s")
    print(f"{args.provider}: {total:.4f} USD cho các câu mới chạy")


# ---------------------------------------------------------------- chấm

SENT = re.compile(r"[.!?](?=\s|$)|\n|;")
# số gắn với khoản ngoài danh mục (nằm giữa tên chỉ tiêu và con số), hoặc % không phải mức thay đổi của chỉ tiêu
OTHER_ITEM = re.compile(r"(?i)hoạt động khác|thu nhập khác|tổng tài sản|dư nợ|cho vay|tiền gửi|huy động|vốn chủ|nợ xấu|"
                        r"trong đó|đóng góp|bằng|chiếm|kế hoạch|thị phần|tỷ trọng|casa|\broe\b|\broa\b|\bnim\b|p/e|"
                        r"trước (?:chi phí )?dự phòng|công ty con|(?<!cổ đông )ngân hàng mẹ|riêng lẻ|trung vị|trung bình|bình quân|"
                        r"lưu chuyển|dòng tiền|thay vì|trình bày lại|bị sửa|soát xét|kiểm toán")
WINDOW = 60                  # khoản ngoài danh mục nằm trong chừng này ký tự trước số (hoặc 15 ký tự sau) thì số không kiểm được
NOT_COMPANY = {"USD", "VND", "CIR", "NIM", "ROE", "ROA", "GDP", "EPS", "CEO", "TTM", "YOY", "QOQ", "KQKD"}
# tên chung trong câu -> thêm chỉ tiêu chuẩn được coi là cùng nghĩa ("doanh thu" có thể là doanh thu trước giảm trừ)
EXTRA_KEYS = {"doanh thu": ("revenue_gross",), "lợi nhuận": ("npat",), "lãi ròng": ("npat",), "lnst": ("npat",),
              "lợi nhuận sau thuế": ("npat",), "lợi nhuận ròng": ("npat",)}
EXTRA = ("revenue_gross",)


def sentences(text: str) -> list[str]:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)          # bỏ đường link markdown, giữ chữ
    text = text.replace("**", "")
    return [s for s in SENT.split(text) if s.strip()]


class Reference:
    """Số đã kiểm chứng: kỳ được hỏi (`main`) và các kỳ/cách tính gần đó (`others`: lũy kế thay vì riêng quý, quý trước,
    cùng kỳ năm trước, lũy kế đến quý trước, bán niên). Mã nào được nhắc cũng chấm, không chỉ mã trong câu hỏi."""

    def __init__(self, conn, plan):
        from services.analyst import store
        self.conn, self.plan, self.store = conn, plan, store
        self.known = {t for (t,) in conn.execute("SELECT ticker FROM companies")}
        self._cache: dict = {}

    def _load(self, ticker, year, period, basis):
        k = (ticker, year, period, basis)
        if k not in self._cache:
            self._cache[k] = self.store.load_ticker(self.conn, ticker, year, period, basis, with_flags=False,
                                                    extra=EXTRA)
        return self._cache[k]

    def main(self, ticker):
        p = self.plan
        return self._load(ticker, p.year, p.period, p.basis)

    def previous_quarter(self, ticker):
        p = self.plan
        if not p.period.startswith("Q") or p.basis != "quarter":
            return None
        q = int(p.period[1])
        return self._load(ticker, *((p.year, f"Q{q - 1}") if q > 1 else (p.year - 1, "Q4")), "quarter")

    def others(self, ticker):
        p = self.plan
        periods = [(p.year, p.period, "ytd" if p.basis == "quarter" else "quarter"), (p.year - 1, p.period, p.basis)]
        if p.period.startswith("Q"):
            q = int(p.period[1])
            periods.append((p.year, f"Q{q - 1}", "quarter") if q > 1 else (p.year - 1, "Q4", "quarter"))
            if q > 1:
                periods.append((p.year, f"Q{q - 1}", "ytd"))
            if q == 2:
                periods.append((p.year, "H1", "ytd"))
        if p.period == "H1":
            periods.append((p.year, "Q2", "quarter"))
        return [d for y, per, b in periods if (d := self._load(ticker, y, per, b)) is not None]


def _candidates(d, key: str, kind: str) -> list:
    """Các số coi là đúng cho (mã, chỉ tiêu) ở một kỳ: kỳ này, cùng kỳ, mức thay đổi (tiền), % thay đổi so với cùng kỳ;
    tỷ lệ: mức hai kỳ và thay đổi theo điểm %."""
    from services.analyst.facts import growth, is_ratio, pair_of
    from services.analyst.guard import Num
    p = pair_of(d, key) if d is not None else None
    if p is None:
        return []
    ratio = is_ratio(d.kind, key)
    vals = []
    if kind == "money" and not ratio:
        vals = [v for v in (p.cur, p.prev) if v is not None]
        if p.cur is not None and p.prev is not None:
            vals.append(p.cur - p.prev)
    elif kind in ("pct", "pp"):
        if ratio and kind == "pct":
            vals = [v for v in (p.cur, p.prev) if v is not None]
        g = growth(d, key)
        if g is not None and (kind == "pp") == ratio:
            vals.append(g)
        elif not ratio and kind == "pct" and p.cur is not None and p.prev and key not in ("pbt", "npat", "npat_parent"):
            vals.append((p.cur - p.prev) / abs(p.prev) * 100)
    return [Num(Decimal(v), kind, 0, Decimal(1)) for v in vals]


def _versus_previous_quarter(d, before, key: str, kind: str) -> list:
    """% thay đổi so với quý liền trước ("tăng 47,6% so với quý I")."""
    from services.analyst.facts import is_ratio, pair_of
    from services.analyst.guard import Num
    if d is None or before is None or kind != "pct" or is_ratio(d.kind, key):
        return []
    a, b = pair_of(d, key), pair_of(before, key)
    if a is None or b is None or a.cur is None or not b.cur:
        return []
    return [Num(Decimal((a.cur - b.cur) / abs(b.cur) * 100), "pct", 0, Decimal(1))]


RANK = {"đúng": 0, "khác kỳ": 1, "sai": 2, "không kiểm được": 3}


def classify(n, ticker: str, name: str, ref: Reference) -> str:
    from services.analyst import catalog
    from services.analyst.guard import NAME_KEYS, matches
    main, before = ref.main(ticker), ref.previous_quarter(ticker)
    keys = list(NAME_KEYS.get(name, ())) + list(EXTRA_KEYS.get(name, ()))
    keys = [k for k in keys if main is None or catalog.name(main.kind, k) or k in EXTRA + ("npat",)]
    cands = [c for k in keys for c in _candidates(main, k, n.kind)]
    if any(matches(n, c) for c in cands):
        return "đúng"
    other = [c for k in keys for d in ref.others(ticker) for c in _candidates(d, k, n.kind)]
    other += [c for k in keys for c in _versus_previous_quarter(main, before, k, n.kind)]
    if any(matches(n, c) for c in other):
        return "khác kỳ"
    return "sai" if cands else "không kiểm được"


def _names(low: str) -> list[tuple[int, int, str]]:
    """(đầu, cuối, tên) các tên chỉ tiêu trong câu, khớp tên dài nhất, không chồng lên nhau."""
    from services.analyst.guard import VOCAB
    occ = sorted(((m.start(), m.end(), n) for n in VOCAB for m in re.finditer(r"(?<!\w)" + re.escape(n) + r"(?!\w)", low)),
                 key=lambda x: x[0] - x[1])
    taken: list[tuple[int, int, str]] = []
    for s, e, n in occ:
        if not any(s < te and ts < e for ts, te, _ in taken):
            taken.append((s, e, n))
    return sorted(taken)


def advice(s: str) -> bool:
    """Câu mang ý khuyến nghị, đọc như bộ kiểm tra số của agent: "không đưa khuyến nghị" (phủ định) không tính."""
    from services.analyst.guard import ADVICE, _negated
    return any(not (m.group(0).lower() == "khuyến nghị" and _negated(s, m.start())) for m in ADVICE.finditer(s))


SUBJECT_SPAN = 40          # mã nằm trong chừng này ký tự đầu câu được coi là chủ ngữ, mang sang câu sau


def score_text(text: str, ref: Reference, log: list | None = None) -> Counter:
    """Đếm con số theo loại (CATS) và số câu mang ý khuyến nghị. Mỗi số tiền hoặc % được thử với mọi mã (mã nhắc trong
    câu, hoặc chủ ngữ của câu trước nếu câu không nhắc mã nào trước số đó) và mọi tên chỉ tiêu nhắc trong câu, lấy kết quả
    tốt nhất; "sai" nghĩa là không khớp cặp mã–chỉ tiêu nào của câu. Không kiểm được: câu không nêu chỉ tiêu trong danh
    mục, số gắn với khoản ngoài danh mục, số nằm trong ngoặc kép, công ty ngoài danh sách theo dõi."""
    from services.analyst.guard import numbers, with_tickers
    tally = Counter()
    last_ticker = None
    for sent in sentences(text):
        s = with_tickers(sent)
        low = s.lower()
        hidden = [(m.start(), m.end()) for m in re.finditer(r"\([^)]*\)|“[^”]*”|\"[^\"]*\"", s)]
        inside = lambda pos: any(a <= pos < b for a, b in hidden)       # noqa: E731
        tick = [(m.start(), m.group(0)) for m in re.finditer(r"\b[A-Z]{3}\b", s)
                if not inside(m.start()) and m.group(0) not in NOT_COMPANY]
        names = _names(low)
        for n in numbers(s):
            if n.kind not in ("money", "pct", "pp"):
                continue
            before_t = [x for pos, x in tick if pos < n.start]
            whos = [before_t[-1]] if before_t else [last_ticker] if last_ticker else []
            whos += [x for _, x in tick if x not in whos]
            before_n = [x for x in names if x[1] <= n.start]
            seg = (low[max(0, n.start - WINDOW):n.start] + " " + low[n.end:n.end + 15] + " "
                   + low[before_n[-1][1] if before_n else 0:n.start])
            cat = "không kiểm được"
            if any(a <= n.start < b and s[a] in "“\"" for a, b in hidden) or OTHER_ITEM.search(seg) or not names:
                cat = "không kiểm được"
            else:
                tries = [classify(n, t, nm, ref) for t in whos if t in ref.known for _, _, nm in names]
                if whos and whos[0] not in ref.known:
                    tries = []          # công ty ngoài danh sách theo dõi đứng ngay trước số
                cat = min(tries, key=RANK.get) if tries else "không kiểm được"
            tally[cat] += 1
            if log is not None:
                log.append((cat, s[n.start:n.end], whos[:1], [x[2] for x in names], s.strip()[:160]))
        subject = [x for pos, x in tick if pos < SUBJECT_SPAN]
        if subject:
            last_ticker = subject[0]
    tally["trả lời có lời khuyên mua bán"] = int(any(advice(s) for s in sentences(text)))
    return tally


def plan_for(conn, g: dict):
    from services.analyst import store
    from services.analyst.plan import Plan, check_plan
    e = agent_eval.write_case(g)["expect"]
    plan = Plan(e["kind"], e["tickers"], e["year"], e["period"], e["basis"], [], [], e["advice_request"],
                e.get("sector", "all"), e.get("measure", "growth"))
    known = {t for (t,) in conn.execute("SELECT ticker FROM companies")}
    return check_plan(plan, known, lambda t: False, lambda ts: store.latest(conn, ts), year_now=agent_eval.TODAY.year,
                      latest_all=lambda sector: store.latest_all(conn, sector)).plan


def agent_text(provider: str, i: int) -> str | None:
    c = agent_eval.load_caches(provider, "write").get(str(i))
    if not c or c.get("status") != "done":
        return None
    return "\n".join(s["text"] for sec in c["result"]["draft"]["sections"] for s in sec["sentences"])


def cmd_score(args) -> None:
    from services.db import connect
    gold = {g["id"]: g for g in agent_eval.load_golden()}
    rows: dict[str, Counter] = {}
    usd: dict[str, float] = {}
    with connect() as conn:
        for i in IDS:
            ref = Reference(conn, plan_for(conn, gold[i]))
            for p in ("anthropic", "openai"):
                f = root(p) / f"{i}.json"
                if f.exists():
                    got = json.loads(f.read_text(encoding="utf-8"))
                    name = f"trợ lý đa năng {got['model']}"
                    rows.setdefault(name, Counter()).update(score_text(got["answer"], ref) | {"câu hỏi": 1})
                    usd[name] = usd.get(name, 0.0) + got["usd"]
                    if args.verbose:
                        print(f"[{i}] {name}: {dict(score_text(got['answer'], ref))}")
                text = agent_text(p, i)
                if text:
                    name = f"agent Soi ({p})"
                    rows.setdefault(name, Counter()).update(score_text(text, ref) | {"câu hỏi": 1})
    for name, c in rows.items():
        n = sum(c[k] for k in CATS)
        print(f"{name}: {c['câu hỏi']} câu hỏi, {n} con số: " + ", ".join(f"{k} {c[k]}" for k in CATS)
              + f"; câu trả lời có lời khuyên mua bán {c['trả lời có lời khuyên mua bán']}" + (f"; {usd[name]:.3f} USD" if name in usd else ""))


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--provider", required=True, choices=["anthropic", "openai"])
    r.add_argument("--model", required=True)
    r.add_argument("--ids")
    s = sub.add_parser("score")
    s.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    {"run": cmd_run, "score": cmd_score}[args.cmd](args)


if __name__ == "__main__":
    main()
