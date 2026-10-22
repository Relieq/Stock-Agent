"""Tìm và chép thuyết minh của một dòng KQKD, kiểm bằng phép cộng (Baocao/dinh-huong/agent-nguyen-nhan.md mục 3.2).

- Tìm trang: mục thuyết minh in theo số tăng dần sau ba báo cáo, nên chia đôi khoảng trang, mỗi lần mô hình đọc tiêu đề
  mục trên một trang (ảnh nhỏ, rẻ). Tiêu đề đã đọc lưu theo tài liệu, dùng lại cho mọi dòng.
- Chép: mô hình chép nguyên văn bảng của mục (tên khoản, số từng cột, dòng tổng); code đọc số.
- Kiểm: tìm cột có tổng các khoản (hoặc dòng tổng) bằng đúng số của dòng trên KQKD đã kiểm chứng ở kỳ này và ở cùng kỳ;
  đơn vị của thuyết minh có thể khác KQKD nên thử các bậc nghìn. Không khớp thì không dùng.

Kết quả lưu ở Data/raw/notes/<id tài liệu>.json; chạy lại không gọi mô hình.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal

from services.extraction.numbers import infer_thousands_sep, parse_amount
from services.ingestion.registry import raw_data_dir

HEAD_LONG_SIDE = 1100        # đọc tiêu đề mục: chữ in đậm, ảnh nhỏ là đủ
TABLE_LONG_SIDE = 2000       # chép bảng: như bước chép báo cáo
MAX_NOTE_PAGES = 3
MAX_SECTION_SCAN = 40        # số trang tối đa đọc lùi từ cuối để tìm đầu một phần thuyết minh

HEAD_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["headings"], "properties": {
    "headings": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                            "required": ["number", "title"],
                                            "properties": {"number": {"type": "string"}, "title": {"type": "string"}}}}}}
HEAD_PROMPT = """Ảnh là một trang báo cáo tài chính của doanh nghiệp Việt Nam, thường thuộc phần thuyết minh. Liệt kê các tiêu đề
MỤC thuyết minh BẮT ĐẦU trên trang này: dòng tiêu đề có số thứ tự mục ở đầu (ví dụ "27. DOANH THU THUẦN", "5. TIỀN",
"VI.25 Chi phí tài chính"). Chép nguyên văn số thứ tự và tên mục. Chỉ lấy mục cấp lớn nhất; bỏ mục con kiểu a), b), (i),
5.1 và bỏ tên dòng trong bảng. Trang không có tiêu đề mục nào thì trả danh sách rỗng."""

_STR = {"type": ["string", "null"]}
TABLE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["unit", "columns", "rows"], "properties": {
    "unit": _STR,
    "columns": {"type": "array", "items": {"type": "string"}},
    "rows": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                        "required": ["label", "values", "is_total"],
                                        "properties": {"label": {"type": "string"},
                                                       "values": {"type": "array", "items": _STR},
                                                       "is_total": {"type": "boolean"}}}}}}
TABLE_PROMPT = """Ảnh là các trang thuyết minh báo cáo tài chính. Chép BẢNG SỐ của mục thuyết minh số {number}
({title}), nguyên văn như in:
- columns: tiêu đề từng cột số theo thứ tự trái sang phải (ví dụ "Quý 3/2026", "Từ 1/1/2026 đến 30/9/2026", "Kỳ trước").
- rows: mỗi dòng một khoản: label là tên khoản; values là các số theo đúng thứ tự columns, chép nguyên văn (giữ dấu chấm,
  phẩy, ngoặc); ô trống hoặc gạch ngang thì null. is_total = true cho dòng tổng cộng của bảng ("Cộng", "Tổng cộng").
- unit: đơn vị tính in trên trang (ví dụ "Triệu VND", "VND"), không thấy thì null.
Chỉ chép bảng của mục {number}; bỏ bảng của mục khác và bỏ lời văn. Mục không có bảng số thì rows rỗng."""


def note_number(text: str | None) -> int | None:
    """Số mục từ số thuyết minh in trên BCTC hoặc tiêu đề: "27" -> 27, "VI.25" -> 25, "5.1" -> 5."""
    if not text:
        return None
    text = re.sub(r"^\s*[IVXLC]+\s*[.\-]\s*", "", text.strip())
    m = re.match(r"\D*(\d+)", text)
    return int(m.group(1)) if m else None


def note_numbers(text: str | None) -> list[int]:
    """Mọi số mục trong ô thuyết minh của một dòng: "26, 28" -> [26, 28]; "24.1" -> [24]; "VI.25" -> [25]."""
    out = []
    for part in re.split(r"[,;&]|\s+và\s+", text or ""):
        n = note_number(part)
        if n is not None and n not in out:
            out.append(n)
    return out


ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_value(text: str | None) -> int | None:
    """"VI." -> 6; chuỗi không phải số La Mã -> None."""
    m = re.fullmatch(r"\s*([IVXLC]+)\s*\.?\s*", text or "")
    if not m:
        return None
    vals = [ROMAN[c] for c in m.group(1)]
    return sum(-v if i + 1 < len(vals) and v < vals[i + 1] else v for i, v in enumerate(vals))


def note_refs(text: str | None) -> list[tuple[int | None, int]]:
    """(phần, số mục) trong ô thuyết minh của một dòng: "VI.14" -> [(6, 14)]; "26, 28" -> [(None, 26), (None, 28)].
    Nhiều BCTC (VNM, STB, ACB, MBB, HDB, HPG: 18/97 BCTC quý) đánh số mục lại từ 1 trong mỗi phần."""
    out = []
    for part in re.split(r"[,;&]|\s+và\s+", text or ""):
        m = re.match(r"\s*([IVXLC]+)\s*[.\-]\s*\d", part)
        sec = roman_value(m.group(1)) if m else None
        n = note_number(part)
        if n is not None and (sec, n) not in out:
            out.append((sec, n))
    return out


def ref_text(sec: int | None, n: int) -> str:
    romans = {v: k for k, v in {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8, "IX": 9,
                               "X": 10}.items()}
    return f"{romans.get(sec, sec)}.{n}" if sec else str(n)


@dataclass
class NoteTable:
    number: int
    title: str
    pages: list[int]
    items: list[tuple[str, Decimal, Decimal]] = field(default_factory=list)   # tên khoản, kỳ này, cùng kỳ (đồng)
    verified: bool = False         # tổng các khoản bằng dòng KQKD ở cả hai kỳ
    period: str = ""               # quarter / ytd: cột của thuyết minh khớp với kỳ nào của KQKD
    note: str = ""


class Notes:
    """Thuyết minh của một BCTC: tìm trang, chép, kiểm. `pdf`: tài liệu pymupdf đã mở; `first_page`: trang đầu sau ba
    báo cáo."""

    def __init__(self, document_id: int, pdf, first_page: int, client=None, render=None):
        self.document_id, self.pdf, self.first_page, self.client = document_id, pdf, first_page, client
        if render is None:
            from services.extraction.sources import render_page
            render = lambda p, side: render_page(pdf, p, side)       # noqa: E731
        self.render = render
        self.path = raw_data_dir() / "notes" / f"{document_id}.json"
        self.cache = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else \
            {"headings": {}, "tables": {}}

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1), encoding="utf-8")

    @property
    def last_page(self) -> int:
        return self.pdf.page_count

    def headings(self, page: int) -> list[tuple[int, str]]:
        key = str(page)
        if key not in self.cache["headings"]:
            data = self.client.json_from_images(HEAD_PROMPT, [(f"Trang {page}", self.render(page, HEAD_LONG_SIDE))],
                                                HEAD_SCHEMA, "notes_heading")
            self.cache["headings"][key] = [[h["number"], h["title"]] for h in data["headings"]]
            self._save()
        return [(n, t) for raw, t in self.cache["headings"][key]
                if roman_value(raw) is None and (n := note_number(raw)) is not None]

    def romans(self, page: int) -> list[int]:
        """Tiêu đề phần (I, II, ..., VI) bắt đầu trên trang."""
        self.headings(page)
        return [v for raw, _ in self.cache["headings"][str(page)] if (v := roman_value(raw)) is not None]

    def section_range(self, section: int) -> tuple[int, int] | None:
        """(trang đầu, trang cuối) của phần `section`: đọc lùi từ cuối tài liệu tới trang có tiêu đề phần đó (hoặc một
        phần đứng trước nó); trang có tiêu đề phần đứng sau là giới hạn cuối. Lưu lại theo tài liệu."""
        key = str(section)
        cached = self.cache.setdefault("sections", {}).get(key)
        if cached is not None:
            return tuple(cached) if cached else None
        hi, found = self.last_page, None
        for page in range(self.last_page, max(self.first_page, self.last_page - MAX_SECTION_SCAN) - 1, -1):
            rs = self.romans(page)
            if any(r > section for r in rs):
                hi = page - 1 if not any(r == section for r in rs) else page
            if any(r <= section for r in rs):
                found = (page, hi)
                break
        self.cache["sections"][key] = list(found) if found else []
        self._save()
        return found

    def find(self, number: int, section: int | None = None) -> tuple[int, str] | None:
        """(trang bắt đầu, tên mục) của mục `number` (trong phần `section` nếu BCTC đánh số theo phần): chia đôi theo
        số mục trên các trang đã đọc."""
        lo, hi = self.first_page, self.last_page
        if section is not None:
            rng = self.section_range(section)
            if rng is None:
                return None
            lo, hi = rng
        for _ in range(12):
            if lo > hi:
                break
            mid = (lo + hi) // 2
            page, nums = mid, self.headings(mid)
            while not nums and page < hi:         # trang không có tiêu đề mục: xem trang sau
                page += 1
                nums = self.headings(page)
            hit = next(((page, t) for n, t in nums if n == number), None)
            if hit:
                return hit
            if not nums or min(n for n, _ in nums) > number:
                hi = mid - 1
            else:
                lo = page + 1
        # Không thấy bằng chia đôi (số mục đánh lại từ đầu ở phần sau, trang khó đọc): xem lần lượt quanh chỗ dừng
        for page in range(max(self.first_page, lo - 2), min(self.last_page, lo + 2) + 1):
            hit = next(((page, t) for n, t in self.headings(page) if n == number), None)
            if hit:
                return hit
        return None

    def pages_of(self, number: int, start: int) -> list[int]:
        """Các trang của mục: từ trang bắt đầu tới trước trang có mục số lớn hơn (tối đa MAX_NOTE_PAGES)."""
        pages = [start]
        if any(n > number for n, _ in self.headings(start)):
            return pages
        for page in range(start + 1, min(self.last_page, start + MAX_NOTE_PAGES - 1) + 1):
            nums = self.headings(page)
            if any(n > number for n, _ in nums):
                if not any(n == number for n, _ in nums):
                    # Mục sau bắt đầu ở giữa trang này: phần đầu trang có thể còn bảng của mục đang chép
                    pages.append(page)
                break
            pages.append(page)
        return pages

    def table(self, number: int, section: int | None = None) -> dict | None:
        """Bảng thô của mục (đã lưu, hoặc tìm trang rồi chép)."""
        key = ref_text(section, number)
        if key not in self.cache["tables"]:
            found = self.find(number, section)
            if found is None:
                self.cache["tables"][key] = None
            else:
                start, title = found
                pages = self.pages_of(number, start)
                images = [(f"Trang {p}", self.render(p, TABLE_LONG_SIDE)) for p in pages]
                data = self.client.json_from_images(TABLE_PROMPT.format(number=number, title=title), images,
                                                    TABLE_SCHEMA, "notes_table")
                self.cache["tables"][key] = data | {"title": title, "pages": pages}
            self._save()
        return self.cache["tables"][key]


SCALES = (Decimal(1), Decimal(10) ** 3, Decimal(10) ** 6, Decimal(10) ** 9)


def match_note(raw: dict | None, number: int, pairs: dict[str, tuple[Decimal, Decimal]], tolerance: Decimal) -> NoteTable:
    """Đọc số trong bảng thô và tìm cặp cột (kỳ này, cùng kỳ) khớp dòng KQKD. `pairs`: kỳ ("quarter"/"ytd") -> (kỳ này,
    cùng kỳ) của dòng KQKD (đồng; so giá trị tuyệt đối vì chi phí có thể in số âm). Thuyết minh quý hay chỉ in lũy kế
    nên thử cả hai kỳ. Khoản con chỉ được dùng khi cộng đúng (cộng hết, hoặc khoản đầu trừ các khoản sau như doanh thu
    trừ giảm trừ); chỉ dòng tổng khớp thì báo rõ."""
    if not raw:
        return NoteTable(number, "", [], note="không tìm thấy mục thuyết minh")
    nt = NoteTable(number, raw.get("title", ""), raw.get("pages", []))
    rows = raw.get("rows") or []
    if not rows:
        nt.note = "mục thuyết minh không có bảng số"
        return nt
    sep = infer_thousands_sep([v for r in rows for v in r["values"]])
    ncol = max(len(r["values"]) for r in rows)
    val = lambda r, j: parse_amount(r["values"][j], sep) if j < len(r["values"]) else None   # noqa: E731
    items = [r for r in rows if not r["is_total"] and any(v is not None for v in r["values"])]
    totals = [r for r in rows if r["is_total"]]

    def sums(j: int):
        """(cách tính, tổng, dấu từng khoản) có thể có ở cột j."""
        vs = [val(r, j) or Decimal(0) for r in items]
        if any(val(r, j) is not None for r in items):
            yield "items", sum(vs, Decimal(0)), [1] * len(vs)
            if len(vs) > 1:
                yield "items", vs[0] - sum((abs(v) for v in vs[1:]), Decimal(0)), [1] + [-1] * (len(vs) - 1)
        if totals and val(totals[-1], j) is not None:
            yield "total", val(totals[-1], j), None

    for kind_wanted in ("items", "total"):
        for period, (cur, prev) in pairs.items():
            if cur is None or prev is None:
                continue
            for scale in SCALES:
                hits = {}
                # Sai số: mức làm tròn của KQKD, hoặc mỗi khoản cộng lệch tối đa một đơn vị in của thuyết minh
                tol = max(tolerance, scale * (len(items) + 1))
                for target, name in ((cur, "cur"), (prev, "prev")):
                    for j in range(ncol):
                        hit = next((sg for kind, sm, sg in sums(j) if kind == kind_wanted
                                    and abs(abs(sm) * scale - abs(target)) <= tol), False)
                        if hit is not False:
                            hits[name] = (j, hit)
                            break
                if len(hits) == 2 and hits["cur"][0] != hits["prev"][0]:
                    (jc, signs), (jp, _) = hits["cur"], hits["prev"]
                    nt.period, nt.verified = period, kind_wanted == "items"
                    signs = signs or [1] * len(items)
                    nt.items = [(r["label"], sg * abs(val(r, jc) or Decimal(0)) * scale if sg < 0 else
                                 (val(r, jc) or Decimal(0)) * scale,
                                 sg * abs(val(r, jp) or Decimal(0)) * scale if sg < 0 else (val(r, jp) or Decimal(0)) * scale)
                                for r, sg in zip(items, signs)]
                    if not nt.verified:
                        nt.note = "dòng tổng khớp KQKD nhưng các khoản con cộng không ra tổng (bảng có khoản lồng nhau)"
                    return nt
    block = _find_block(rows, val, ncol, pairs, tolerance)
    if block is not None:
        period, scale, jc, jp, kids, anchor = block
        nt.period, nt.verified = period, True
        nt.items = [(r["label"], (val(r, jc) or Decimal(0)) * scale, (val(r, jp) or Decimal(0)) * scale) for r in kids]
        nt.note = f"khối \"{anchor}\" trong bảng (bảng gồm nhiều dòng KQKD)"
        return nt
    nt.note = "tổng các khoản không bằng dòng KQKD ở kỳ này và cùng kỳ"
    return nt


MAX_BLOCK = 15


def _find_block(rows, val, ncol, pairs, tolerance):
    """Bảng gồm nhiều dòng KQKD (MWG quý 2/2026: một bảng có cả chi phí bán hàng và chi phí quản lý, mỗi khối có khoản
    con riêng): tìm một dòng bằng dòng KQKD ở cả kỳ này và cùng kỳ, rồi các dòng liền dưới (dòng đầu khối) hoặc liền
    trên (dòng tổng cuối khối) cộng ra đúng dòng đó ở cả hai cột. Trả về (kỳ, bậc đơn vị, cột kỳ này, cột cùng kỳ, các
    dòng con, tên dòng neo) hoặc None."""
    numeric = [r for r in rows if any(v is not None for v in r["values"])]
    for period, (cur, prev) in pairs.items():
        if cur is None or prev is None:
            continue
        for scale in SCALES:
            for jc in range(ncol):
                for jp in range(ncol):
                    if jc == jp:
                        continue
                    near = lambda v, t, n: v is not None and abs(abs(v) * scale - abs(t)) <= max(tolerance, scale * n)  # noqa: E731
                    for i, r in enumerate(numeric):
                        if not (near(val(r, jc), cur, 2) and near(val(r, jp), prev, 2)):
                            continue
                        for step in (1, -1):
                            sc = sp = Decimal(0)
                            kids = []
                            k = i + step
                            while 0 <= k < len(numeric) and len(kids) < MAX_BLOCK:
                                kids.append(numeric[k])
                                sc += val(numeric[k], jc) or Decimal(0)
                                sp += val(numeric[k], jp) or Decimal(0)
                                if len(kids) > 1 and near(sc, cur, len(kids) + 1) and near(sp, prev, len(kids) + 1):
                                    return period, scale, jc, jp, kids if step == 1 else kids[::-1], r["label"]
                                k += step
    return None


def as_dict(nt: NoteTable) -> dict:
    d = asdict(nt)
    d["items"] = [[lab, str(a), str(b)] for lab, a, b in nt.items]
    return d
