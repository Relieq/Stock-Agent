"""Agent tìm nguyên nhân biến động LNST của một BCTC đã kiểm chứng (Baocao/dinh-huong/agent-nguyen-nhan.md mục 3.3-3.5).

1. Code tách mức thay đổi LNST theo dòng KQKD (decompose.py), cả riêng quý và lũy kế.
2. Vòng agent, tối đa MAX_STEPS lượt, dừng sớm khi chi phí chạm MAX_USD: mỗi lượt mô hình xem bảng tách và những gì đã
   thu thập, chọn một việc: đọc thuyết minh của một dòng (notes.py, chỉ dùng khoản con cộng đúng), lấy nguyên nhân công
   ty nêu trong công văn giải trình (đã đối chiếu BCTC), hoặc dừng.
3. Code dựng bảng số (mỗi dòng có nguồn), mô hình viết 2-5 câu, bộ kiểm tra số của agent báo cáo kiểm từng câu; câu sai
   được viết lại tối đa 2 lần rồi bỏ.

Kết quả lưu ở Data/raw/causes/<id tài liệu>.json.
"""

from __future__ import annotations

import json
from decimal import Decimal

from services.analyst.guard import check_draft
from services.analyst.sheet import FactSheet
from services.causes.decompose import Breakdown, decompose_any, top_parts
from services.causes.notes import Notes, match_note, note_refs, ref_text
from services.extraction.rules import RULESETS
from services.ingestion.registry import raw_data_dir
from services.metrics.card import ty

MAX_STEPS = 4
MAX_USD = 0.03
REWRITES = 2
PERIOD_WORDS = {"quarter": "quý {q}/{y}", "ytd": "lũy kế {m} tháng năm {y}"}
MONTHS = {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12}

STEP_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["action", "line", "why"], "properties": {
    "action": {"type": "string", "enum": ["note", "letter", "done"]},
    "line": {"type": "string"}, "why": {"type": "string"}}}
STEP_PROMPT = """Bạn giúp tìm nguyên nhân LNST của {ticker} {period} thay đổi so với cùng kỳ. Code đã tách mức thay đổi theo
từng dòng của KQKD (số đã kiểm chứng, đơn vị tỷ đồng; đóng góp dương là làm LNST tăng):
{breakdown}

Đã thu thập:
{gathered}

Chọn MỘT việc tiếp theo để giải thích các dòng đóng góp lớn nhất:
- "note": đọc thuyết minh của một dòng (line = mã dòng trong bảng trên, chỉ dòng có ghi "có thuyết minh"); thuyết minh
  tách dòng đó thành các khoản con (ví dụ thu nhập lãi từ cho vay, từ tiền gửi).
- "letter": lấy nguyên nhân công ty nêu trong công văn giải trình (chỉ khi bảng ghi "có công văn"; line để trống).
- "done": đã đủ để giải thích, hoặc không còn việc gì đáng làm.
Không chọn lại việc đã làm. why: một câu ngắn vì sao."""

WRITE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["sentences"], "properties": {
    "sentences": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                             "required": ["text", "uses"],
                                             "properties": {"text": {"type": "string"},
                                                            "uses": {"type": "array", "items": {"type": "string"}}}}}}}
WRITE_PROMPT = """Viết 2 đến 5 câu tiếng Việt giải thích vì sao LNST {target} của {ticker} {period} thay đổi so với cùng kỳ,
cho người đọc phổ thông. Chỉ dựa vào bảng số dưới đây (số do code tính từ BCTC đã kiểm chứng; mỗi dòng có mã S...):
{sheet}

Cách viết:
- Câu đầu nói LNST thay đổi bao nhiêu; các câu sau nói các dòng đóng góp lớn nhất ở CẢ HAI chiều (làm tăng và làm giảm)
  và, nếu có, khoản con trong thuyết minh hay nguyên nhân công ty nêu. Không bỏ một dòng lớn trong bảng để chọn dòng nhỏ.
- Các khoản con trong cùng một thuyết minh là các khoản ngang nhau: không viết "trong đó" giữa hai khoản con.
- Số ghi "âm ... (hoàn nhập hoặc lợi ích)" là khoản làm giảm chi phí; số ghi "lỗ" là lỗ: giữ đúng như vậy trong câu.
- Mỗi dòng bảng số đã ghi rõ kỳ (riêng quý hay lũy kế). Viết đúng kỳ của dòng đó; không gán số lũy kế cho riêng quý,
  không rào đón về kỳ khi dòng đã ghi rõ.
- Mỗi câu ghi trong "uses" mã các dòng bảng số câu dùng. Chỉ dùng con số có trong các dòng đã ghi, chép đúng như bảng
  (được làm tròn bớt). Không tự tính số mới. Từ tăng/giảm phải đúng như bảng.
- Nguyên nhân ghi "theo công ty" thì viết rõ là theo công ty. Không khuyến nghị mua bán, không nói về giá cổ phiếu.
- Không nhắc mã dòng (S1...) hay mã chỉ tiêu trong câu.
{feedback}"""


def _signed_ty(v: Decimal) -> str:
    return ("+" if v >= 0 else "−") + ty(v)


def _period_label(period: str, year: int, kind: str) -> str:
    return PERIOD_WORDS[kind].format(q=period[1], y=year, m=MONTHS.get(period, 12))


def profit_text(v: Decimal) -> str:
    """Lợi nhuận: số âm ghi "lỗ" (VIC quý 2/2025: cùng kỳ lỗ 941 tỷ từng bị ghi "941 tỷ")."""
    return f"lỗ {ty(v)}" if v < 0 else ty(v)


def part_text(p, label: str, ticker: str, flip: bool = False) -> str:
    """Dòng bảng số cho một dòng KQKD đóng góp vào mức thay đổi LNST.
    - Dòng thu nhập: âm là lỗ, ghi chữ "lỗ" vì số in ra bỏ dấu (VPB quý 3: mua bán chứng khoán kinh doanh lỗ 363 tỷ, từng bị
      viết thành "chỉ còn 363 tỷ").
    - Dòng chi phí: đổi về "chi phí dương" theo cách BCTC in (`flip`: in chi phí thành số âm); chi phí âm là hoàn nhập hoặc
      lợi ích thuế, ghi rõ, và chiều tăng/giảm tính trên số có dấu (GAS quý 2: chi phí quản lý −7,9 tỷ so với −1.283 tỷ là
      chi phí TĂNG 1.275 tỷ; SAB, VRE: thuế hoãn lại đổi từ chi phí sang lợi ích và ngược lại)."""
    if not p.expense:
        cur, prev, show = p.cur, p.prev, profit_text
    else:
        sign = -1 if flip and not p.code.startswith("(") else 1      # phần cổ đông không kiểm soát do code tính
        cur, prev = sign * p.cur, sign * p.prev
        show = lambda v: ty(v) if v >= 0 else f"âm {ty(v)} (hoàn nhập hoặc lợi ích)"     # noqa: E731
    word = "tăng" if cur >= prev else "giảm"
    return (f"{p.label} {label} của {ticker}: {show(cur)}, cùng kỳ {show(prev)} ({word} {ty(cur - prev)}), "
            f"làm LNST {'tăng' if p.effect >= 0 else 'giảm'} {ty(p.effect)}")


def item_text(lab: str, a: Decimal, b: Decimal, expense: bool) -> str:
    """Khoản con trong thuyết minh của một dòng KQKD, đã xoay chiều theo bảng (orient_items). `expense`: dòng đó là khoản
    trừ trong công thức LNST. Khoản âm là khoản đi ngược dòng của nó (hoàn nhập trong dòng chi phí, khoản trừ trong dòng
    thu nhập). Ghi luôn tác động lên LNST để câu không phải tự suy (GAS quý 2: "các khoản dự phòng" (492) so với (1.634)
    tỷ là hoàn nhập ít đi, tức chi phí tăng và LNST giảm, từng bị viết là "làm tăng lợi nhuận")."""
    show = lambda v: ty(v) if v >= 0 else f"âm {ty(v)}"     # noqa: E731
    effect = (b - a) if expense else (a - b)
    return (f"{lab} {show(a)}, cùng kỳ {show(b)} ({'tăng' if a >= b else 'giảm'} {ty(a - b)}), "
            f"làm LNST {'tăng' if effect >= 0 else 'giảm'} {ty(effect)}")


def orient_items(items: list[tuple[str, Decimal, Decimal]]) -> list[tuple[str, Decimal, Decimal]]:
    """Bảng in cả khối trong ngoặc (VRE: doanh thu; VPB: chi phí khác) thì đổi dấu cả khối để tổng dương."""
    total = sum((a for _, a, _ in items), Decimal(0))
    return [(lab, -a, -b) for lab, a, b in items] if total < 0 else items


MAX_PARTS = 6
MIN_PART_SHARE = Decimal("0.1")     # dòng nhỏ hơn 10% dòng đóng góp lớn nhất thì không đưa vào bảng số


def sheet_parts(bd):
    """Các dòng đưa vào bảng số: mọi dòng có đóng góp từ 10% dòng lớn nhất trở lên, cả hai chiều, tối đa 6 (trước đây
    chỉ lấy đủ 80% mức thay đổi theo một chiều nên bỏ sót dòng lớn: VIC lợi nhuận gộp +18.567 tỷ, FPT, VIB)."""
    if not bd.parts:
        return []
    top = max(abs(p.effect) for p in bd.parts)
    return [p for p in bd.parts if abs(p.effect) >= top * MIN_PART_SHARE][:MAX_PARTS]


class CauseAgent:
    def __init__(self, conn, document_id: int, client, facts=None, record=None, notes: Notes | None = None,
                 known: set[str] | None = None):
        from services.extraction.pipeline import _load_record
        from services.metrics.card import Facts
        self.conn, self.doc_id, self.client = conn, document_id, client
        self.record = record or _load_record(conn, document_id)
        self.facts = facts or Facts(document_id, self.record)
        row = conn.execute("SELECT ticker, fiscal_year, fiscal_period, scope FROM documents WHERE id = %s",
                           (document_id,)).fetchone()
        self.ticker, self.year, self.period, self.scope = row
        self.st = self.facts.statements["IS"]
        self.labels = {k: (self.facts.rows[("IS", k)].label if ("IS", k) in self.facts.rows else k)
                       for k in self.st.values}
        tol = self.st.multiplier * 20
        self.bd = {kind: decompose_any(self.facts.template or "", self.st.values, self.labels, self.facts.flip_is, kind,
                                       tol) for kind in ("quarter", "ytd")}
        self.notes = notes if notes is not None else self._notes()
        self.known = known if known is not None else {t for (t,) in conn.execute("SELECT ticker FROM companies")}
        self.gathered: list[dict] = []
        self.steps: list[dict] = []
        self.start_usd = client.usage.usd if client is not None else 0.0

    def _notes(self) -> Notes | None:
        from services.extraction.sources import candidates, open_pdf
        key = self.conn.execute("SELECT storage_key FROM document_files WHERE document_id = %s ORDER BY downloaded_at DESC"
                                " LIMIT 1", (self.doc_id,)).fetchone()
        cand = next((c for c in self.record.get("candidates", []) if c["name"] == self.record.get("chosen")), None)
        if key is None or cand is None:
            return None
        pdf = next((open_pdf(c) for c in candidates(raw_data_dir() / key[0]) if c.name == self.record["chosen"]), None)
        first = max(p for ps in cand["statement_pages"].values() for p in ps) + 1
        return Notes(self.doc_id, pdf, first, self.client) if pdf is not None else None

    # ---------- công cụ ----------

    def note_codes(self, code: str) -> list[tuple[str, tuple[int | None, int]]]:
        """(mã dòng KQKD, (phần, số mục) thuyết minh) của dòng; dòng không in số thuyết minh thì của các dòng trong công
        thức."""
        own = note_refs(getattr(self.facts.rows.get(("IS", code)), "note", None))
        if own:
            return [(code, n) for n in own]
        out = []
        for r in RULESETS.get(self.facts.template, RULESETS["TT200"]).rules:
            if r.statement == "IS" and r.lhs == code:
                for _, c in r.rhs:
                    for k in note_refs(getattr(self.facts.rows.get(("IS", c)), "note", None)):
                        if (c, k) not in out:
                            out.append((c, k))
                break
        return out

    def read_note(self, code: str) -> list[dict]:
        out = []
        seen = {g["number"] for g in self.gathered if g["tool"] == "note"}
        for c, ref in self.note_codes(code):
            sec, n = ref
            if ref_text(*ref) in seen:
                continue                     # nhiều dòng dùng chung một thuyết minh (SSI: doanh thu hoạt động, mục 30)
            seen.add(ref_text(*ref))
            nt, matched = None, c
            same = [c] + [k for k in self.st.values if k != c and
                          ref in note_refs(getattr(self.facts.rows.get(("IS", k)), "note", None))]
            for c2 in same:
                v = self.st.values[c2]
                nt = match_note(self.notes.table(n, sec), n, {"quarter": (v.get("q_cur"), v.get("q_prev_year")),
                                                         "ytd": (v.get("ytd_cur"), v.get("ytd_prev_year"))},
                                self.st.multiplier * 5)
                if nt.items:
                    matched = c2
                    break
            # "line": dòng KQKD mà bảng thật sự khớp (MWG quý 2: thuyết minh 24 gồm cả doanh thu và doanh thu tài chính;
            # đọc cho dòng doanh thu nhưng phần khớp là doanh thu tài chính)
            out.append({"tool": "note", "line": matched, "for": code, "number": ref_text(*ref), "title": nt.title, "pages": nt.pages,
                        "period": nt.period, "verified": nt.verified, "note": nt.note,
                        "items": [[lab, str(a), str(b)] for lab, a, b in nt.items]})
        return out

    def read_letter(self) -> list[dict]:
        from services.metrics.service import explanation
        e = explanation(self.conn, self.ticker, self.year, self.period, self.scope)
        if e is None or not e["view"].read:
            return [{"tool": "letter", "reasons": [], "note": "không có công văn đã đọc"}]
        return [{"tool": "letter", "letter_id": e["id"], "period_kind": e["view"].period_kind,
                 "reasons": [[r.text, r.verdict, r.detail] for r in e["view"].reasons
                             if r.css != "bad"]}]

    def line_is_expense(self, code: str) -> bool:
        """Dòng là khoản trừ trong công thức LNST: theo kết quả tách nếu là dòng lá, không thì theo dấu của dòng trong
        công thức của dòng cha (giá vốn trong lợi nhuận gộp)."""
        bd = self.bd["quarter"]
        part = next((p for p in (bd.parts if bd else []) if p.code == code), None)
        if part is not None:
            return part.expense
        for r in RULESETS.get(self.facts.template, RULESETS["TT200"]).rules:
            if r.statement == "IS":
                for sign, c in r.rhs:
                    if c == code:
                        return sign < 0
        return False

    # ---------- vòng agent ----------

    def _breakdown_text(self) -> str:
        lines = []
        for kind, bd in self.bd.items():
            if bd is None or not bd.ok:
                continue
            lines.append(f"{_period_label(self.period, self.year, kind)}: LNST {ty(bd.prev)} -> {ty(bd.cur)} "
                         f"({_signed_ty(bd.change)})")
            for p in bd.parts[:8]:
                has = "có thuyết minh" if self.note_codes(p.code) else "không có thuyết minh"
                lines.append(f"  [{p.code}] {p.label}: đóng góp {_signed_ty(p.effect)} ({has})")
        if self.letter_available():
            lines.append("Có công văn giải trình của công ty cho kỳ này.")
        return "\n".join(lines)

    def letter_available(self) -> bool:
        from services.metrics.service import explanation
        return explanation(self.conn, self.ticker, self.year, self.period, self.scope) is not None

    def _gathered_text(self) -> str:
        if not self.gathered:
            return "(chưa có)"
        out = []
        for g in self.gathered:
            if g["tool"] == "note":
                part = f" (thuộc dòng {g['for']})" if g.get("for") and g["for"] != g["line"] else ""
                out.append(f"- đã đọc thuyết minh {g['number']} của dòng {g['line']}{part}: "
                           + (f"{len(g['items'])} khoản con, {'cộng khớp' if g['verified'] else g['note']}" if g["items"]
                              else g["note"]))
            else:
                out.append(f"- công văn: {len(g['reasons'])} nguyên nhân dùng được" if g["reasons"]
                           else f"- công văn: {g.get('note') or 'không có nguyên nhân dùng được'}")
        return "\n".join(out)

    def spent(self) -> float:
        return self.client.usage.usd - self.start_usd

    def investigate(self) -> None:
        bd = self.bd["quarter"]
        if bd is None or not bd.ok:
            return
        done: set[tuple[str, str]] = set()
        for _ in range(MAX_STEPS):
            if self.spent() >= MAX_USD:
                self.steps.append({"action": "stop", "why": "chạm trần chi phí"})
                break
            step = self.client.json_from_images(
                STEP_PROMPT.format(ticker=self.ticker, period=_period_label(self.period, self.year, "quarter"),
                                   breakdown=self._breakdown_text(), gathered=self._gathered_text()),
                [], STEP_SCHEMA, "cause_step")
            self.steps.append(step)
            key = (step["action"], step["line"] if step["action"] == "note" else "")
            if step["action"] == "done" or key in done:
                break
            done.add(key)
            if step["action"] == "note" and self.notes is not None and self.note_codes(step["line"]):
                self.gathered += self.read_note(step["line"])
            elif step["action"] == "letter":
                self.gathered += self.read_letter()
            else:
                break

    # ---------- bảng số và lời ----------

    def sheet(self) -> FactSheet:
        sh = FactSheet()
        bd = self.bd["quarter"]
        label = _period_label(self.period, self.year, "quarter")
        src = lambda code, col: [{"document_id": self.doc_id, "page": getattr(self.facts.rows.get(("IS", code)), "page",
                                                                            None), "label": self.labels.get(code, code),
                                 "column": col}]   # noqa: E731
        target = "của cổ đông công ty mẹ" if bd.target in ("61", "b.npat_parent", "201") else ""
        sh.add("metric", f"LNST {target} {label} của {self.ticker}: {profit_text(bd.cur)}, cùng kỳ {profit_text(bd.prev)}, "
                         f"{'tăng' if bd.change >= 0 else 'giảm'} {ty(bd.change)}".replace("  ", " "),
               ticker=self.ticker, metric="npat_parent", direction="up" if bd.change >= 0 else "down",
               sources=src(bd.target, "q_cur"))
        for p in sheet_parts(bd):
            sh.add("cause_part", part_text(p, label, self.ticker, self.facts.flip_is),
                   ticker=self.ticker, names=[p.label.lower()], sources=src(p.code, "q_cur"))
        for g in self.gathered:
            if g["tool"] == "note" and g["items"] and g["verified"]:
                per = _period_label(self.period, self.year, g["period"])
                items = sorted(orient_items([(lab, Decimal(a), Decimal(b)) for lab, a, b in g["items"]]),
                               key=lambda i: -abs(i[1] - i[2]))[:3]
                expense = self.line_is_expense(g["line"])
                for lab, a, b in items:
                    line = self.labels.get(g["line"], g["title"]).strip()
                    sh.add("note_item", f"Thuyết minh của dòng {line} (KQKD), {per} của {self.ticker}: "
                                        + item_text(lab, a, b, expense),
                           ticker=self.ticker, names=[lab.lower()],
                           sources=[{"document_id": self.doc_id, "page": g["pages"][0] if g["pages"] else None,
                                     "label": f"Thuyết minh {g['number']}", "column": g["period"]}])
            elif g["tool"] == "letter":
                for text, verdict, detail in g["reasons"][:4]:
                    from services.analyst.tools import words_only
                    shown = text if verdict == "số khớp BCTC" else words_only(text)
                    sh.add("reason", f"Nguyên nhân {self.ticker} nêu trong công văn giải trình ({verdict}): {shown}",
                           ticker=self.ticker, sources=[{"document_id": g["letter_id"], "page": None,
                                                         "label": "Công văn giải trình"}])
        return sh

    def write(self, sh: FactSheet) -> tuple[list[dict], list[str]]:
        bd = self.bd["quarter"]
        target = "của cổ đông công ty mẹ" if bd.target in ("61", "b.npat_parent", "201") else ""
        feedback: list[str] = []
        kept, dropped = [], []
        for attempt in range(REWRITES + 1):
            fb = ("Bản trước có các câu sai, viết lại cả đoạn và sửa đúng các câu này:\n" + "\n".join(f"- {l}" for l in feedback)
                  if feedback else "")
            draft = self.client.json_from_images(
                WRITE_PROMPT.format(target=target, ticker=self.ticker, period=_period_label(self.period, self.year,
                                                                                           "quarter"),
                                    sheet=sh.prompt_text(), feedback=fb), [], WRITE_SCHEMA, "cause_write")
            sentences = draft["sentences"]
            violations, _, _ = check_draft({"sections": [{"heading": "", "sentences": sentences}]}, sh, {self.ticker},
                                           self.known)
            bad = {v.sentence for v in violations}
            if not bad or attempt == REWRITES:
                kept = [s for i, s in enumerate(sentences) if i not in bad]
                dropped = [f"{sentences[v.sentence]['text']} — {v.kind}: {v.detail}" for v in violations]
                break
            feedback = [f"“{sentences[v.sentence]['text']}”: {v.kind} — {v.detail}" for v in violations]
        return kept, dropped

    def run(self) -> dict:
        bd = self.bd["quarter"]
        out = {"document_id": self.doc_id, "ticker": self.ticker, "period": self.period, "year": self.year}
        if bd is None or not bd.ok:
            out["status"] = "not_explained"
            out["note"] = bd.note if bd else "mẫu BCTC chưa hỗ trợ hoặc thiếu số hai kỳ"
        else:
            self.investigate()
            sh = self.sheet()
            kept, dropped = self.write(sh)
            out.update(status="done" if kept else "failed", sentences=kept, dropped=dropped, sheet=sh.to_json(),
                       steps=self.steps, gathered=self.gathered,
                       explained=str(sum((p.effect for p in top_parts(bd, limit=3)), Decimal(0))),
                       change=str(bd.change))
        out["usd"] = round(self.spent(), 5) if self.client is not None else 0.0
        path = raw_data_dir() / "causes" / f"{self.doc_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        return out


def view(document_id: int) -> dict | None:
    """Kết quả đã lưu cho thẻ KQKD: các câu kèm nguồn (trang BCTC hoặc thuyết minh) của các dòng bảng số câu dùng."""
    path = raw_data_dir() / "causes" / f"{document_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "done":
        return None
    facts = {f["id"]: f for f in data.get("sheet", [])}
    out = []
    for s in data.get("sentences", []):
        sources = []
        for u in s.get("uses", []):
            for src in facts.get(u, {}).get("sources", []):
                key = (src.get("document_id"), src.get("page"), src.get("label"))
                if src.get("page") and key not in [(x["document_id"], x["page"], x["label"]) for x in sources]:
                    sources.append({"document_id": src["document_id"], "page": src["page"], "label": src.get("label", "")})
        out.append({"text": s["text"], "sources": sources})
    return {"sentences": out}


def after_extraction(conn, document_id: int, client) -> str | None:
    """Bộ canh gọi sau khi đọc xong BCTC mới: chạy agent cho BCTC quý đã kiểm chứng hoặc đã duyệt. Trả về dòng báo quản
    trị; lỗi không làm hỏng lượt canh."""
    if client is None:
        return None
    row = conn.execute("SELECT status, doc_type FROM documents WHERE id = %s", (document_id,)).fetchone()
    if row is None or row[0] not in ("verified", "approved") or row[1] != "fs_quarter":
        return None
    try:
        r = CauseAgent(conn, document_id, client).run()
    except Exception as e:      # noqa: BLE001
        return f"nguyên nhân biến động: LỖI {e}"
    if r["status"] != "done":
        return f"nguyên nhân biến động: không viết được ({r.get('note') or r['status']})"
    return f"nguyên nhân biến động: {len(r['sentences'])} câu ({r['usd']:.4f} USD)"
