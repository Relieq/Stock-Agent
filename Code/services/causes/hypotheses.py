"""Giả thuyết về nguyên nhân lợi nhuận thay đổi, do code chọn theo ngưỡng số (Baocao/dinh-huong/agent-nguyen-nhan.md
mục 8). Danh sách cố định bốn loại; mô hình không tham gia, câu điền theo mẫu, mỗi số mang nguồn như các số trên thẻ.

Giả thuyết không phải kết luận: mỗi giả thuyết nói điều gì sẽ kiểm được nó, và nếu có công văn giải trình thì ghi công
văn có nhắc tới ý đó hay không (so khớp từ khóa trên lời công ty, không đánh giá lời giải thích).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal

from services.causes.decompose import MINORITY, decompose_any
from services.extraction.bank import clean_label, fold
from services.ingestion.registry import raw_data_dir
from services.metrics.card import CONSOLIDATION_LINE, QUARTERS, Facts, Source, Value, ty, vn

UNVERIFIED = "giả thuyết, chưa kiểm chứng"
COMPUTED = "số tính từ BCTC"

# Ngưỡng (chỉnh trên nửa dev của bộ đo, xem eval/hypotheses.py)
SCOPE_RATIO = Decimal(3)              # phần của cổ đông không kiểm soát đổi ít nhất gấp 3 lần (hoặc còn dưới 1/3)
SCOPE_MATERIAL = Decimal("0.1")       # và mức đổi đó từ 10% mức thay đổi LNST công ty mẹ
JV_RATIO = Decimal(3)                 # lãi công ty liên kết đổi ít nhất gấp 3 lần: chỉ ghi thêm, không đủ một mình
CF_MATERIAL = Decimal("0.05")         # dấu hiệu kèm: dòng LCTT mua/bán công ty con từ 5% LNTT lũy kế
SHRINK = Decimal("0.8")               # dấu hiệu kèm: doanh thu và chi phí bán hàng cùng giảm trên 20%
ONE_OFF_OF_CHANGE = Decimal(1) / 3    # khoản ngoài hoạt động chính đổi từ 1/3 mức thay đổi LNTT
ONE_OFF_OF_PBT = Decimal("0.1")       # và từ 10% LNTT (kỳ lớn hơn)
FLAT_PBT = Decimal("0.1")             # LNTT đổi dưới 10% so với cùng kỳ: coi như đi ngang, không xét khoản một lần
BANK_RATIO = Decimal(2)               # ngân hàng: dòng của quý cao hơn gấp đôi trung bình các quý trước
BANK_MATERIAL = Decimal("0.1")        # và phần vượt trung bình từ 10% LNTT quý
BANK_MIN_HISTORY = 3                  # cần ít nhất 3 trong 4 quý trước

# Từ khóa (đã bỏ dấu) để biết công văn có nhắc tới ý của giả thuyết không
WORDS = {
    "scope": r"cong ty con|hop nhat|ty le so huu|so huu|thoai von|chuyen nhuong|quyen kiem soat|lien doanh|lien ket"
             r"|co dong khong kiem soat",
    "fin": r"tai chinh|ty gia|co tuc|loi nhuan duoc chia|lai tien gui|chuyen nhuong|dau tu|lai vay|chung khoan",
    "other": r"thu nhap khac|chi phi khac|boi thuong|thanh ly|nhuong ban|hoan nhap|xu ly|bat thuong|mot lan",
    "gross": r"doanh thu|san luong|gia ban|bien|gia von|gia nguyen|chi phi dau vao|nhu cau|tieu thu",
    "b.nfee": r"dich vu|bao hiem|thanh toan|thu phi|phi dich vu",
    "b.prov": r"du phong|rui ro|no xau|chat luong tai san",
    "b.nother": r"hoat dong khac|thu hoi no|no da xu ly|xu ly rui ro",
}
LINE_NAMES = {"fin_income": "doanh thu hoạt động tài chính", "fin_expense": "chi phí tài chính",
              "other_profit": "lợi nhuận khác"}
LINE_CHECK = {"fin_income": "tai chinh", "fin_expense": "tai chinh", "other_profit": "khac"}
BANK_LINES = {"net_fee": ("b.nfee", "lãi thuần từ hoạt động dịch vụ"),
              "provision": ("b.prov", "chi phí dự phòng rủi ro tín dụng"),
              "other_profit": ("b.nother", "lãi thuần từ hoạt động khác")}


@dataclass
class Hypothesis:
    kind: str                 # scope / one_off / gross / bank_unusual
    title: str
    text: str
    check: str                # điều sẽ xác nhận hoặc bác bỏ giả thuyết
    label: str = UNVERIFIED   # nhãn hiện kèm (giả thuyết, hoặc số tính được)
    words: str = ""           # khóa trong WORDS để so với công văn
    sources: list[Source] = field(default_factory=list)
    company: str = ""         # "công văn có nhắc tới" / "công văn không nhắc tới" / "chưa có công văn"
    company_text: str = ""    # lý do của công ty khớp từ khóa (nếu có)


def _signed(v: Decimal) -> str:
    return ("−" if v < 0 else "") + ty(v)


def _move(a: Decimal, b: Decimal) -> str:
    """'tăng X (từ b lên a)' / 'giảm X (từ b xuống a)', số có dấu khi âm."""
    return (f"tăng {ty(a - b)} (từ {_signed(b)} lên {_signed(a)})" if a >= b
            else f"giảm {ty(a - b)} (từ {_signed(b)} xuống {_signed(a)})")


def _ratio_change(a: Decimal, b: Decimal, k: Decimal) -> bool:
    """a và b cùng khác 0 mà |a| ≥ k|b| hoặc |a| ≤ |b|/k; hoặc một kỳ bằng 0 còn kỳ kia khác 0."""
    if a == 0 and b == 0:
        return False
    if a == 0 or b == 0:
        return True
    return abs(a) >= k * abs(b) or abs(a) * k <= abs(b)


def _src(*values: Value) -> list[Source]:
    return [v.source for v in values if v is not None and v.source is not None]


def _pair(f: Facts, metric: str, check: str | None = None, expense: bool = False) -> tuple[Value, Value] | None:
    code = f.code("IS", metric)
    if code is None:
        return None
    it = f.rows.get(("IS", code))
    if check and (it is None or check not in fold(clean_label(it.label or ""))):
        return None             # mã dòng theo mẫu không đúng tên (BCTC TT99 in mã TT200): không đoán
    cur, prev = f.get("IS", code, "q_cur", expense), f.get("IS", code, "q_prev_year", expense)
    if cur.value is None or prev.value is None:
        return None
    return cur, prev


# ---------- bốn loại ----------

def scope_change(f: Facts, bd) -> Hypothesis | None:
    """Đổi phạm vi hợp nhất: phần của cổ đông không kiểm soát đổi mạnh, kèm ít nhất một dấu hiệu khác."""
    if f.template == "TCTD" or bd is None or not bd.ok:
        return None
    mi = next((p for p in bd.parts if p.code == MINORITY), None)
    if mi is None or not _ratio_change(mi.cur, mi.prev, SCOPE_RATIO) or not bd.change \
            or abs(mi.cur - mi.prev) < abs(bd.change) * SCOPE_MATERIAL:
        return None
    signs, sources = [], []
    jv = _pair(f, "jv_profit", "lien")
    if jv and _ratio_change(jv[0].value, jv[1].value, JV_RATIO):
        signs.append(f"lãi từ công ty liên doanh, liên kết {_move(jv[0].value, jv[1].value)}")
        sources += _src(*jv)
    strong = False
    pbt_ytd = f.metric("IS", "pbt", "ytd_cur").value
    for (st, code), it in f.rows.items():
        if st != "CF" or not CONSOLIDATION_LINE.search(fold(clean_label(it.label or ""))):
            continue
        v = f.get("CF", code, "ytd_cur")
        if v.value and (not pbt_ytd or abs(v.value) >= abs(pbt_ytd) * CF_MATERIAL):
            signs.append(f"LCTT lũy kế có dòng \"{it.label.strip()}\" {_signed(v.value)}")
            sources += _src(v)
            strong = True
    rev, sell = _pair(f, "revenue"), _pair(f, "selling_expense", expense=True)
    if rev and sell and rev[1].value > 0 and sell[1].value > 0 and rev[0].value < rev[1].value * SHRINK \
            and sell[0].value < sell[1].value * SHRINK:
        signs.append(f"doanh thu thuần {_move(rev[0].value, rev[1].value)} và chi phí bán hàng "
                     f"{_move(sell[0].value, sell[1].value)}")
        sources += _src(*rev, *sell)
        strong = True
    if not strong:
        return None             # lãi công ty liên kết đổi một mình chưa đủ (VIC quý 4/2025: phần không kiểm soát lỗ
                                # sâu hơn vì công ty con lỗ, không phải đổi sở hữu)
    return Hypothesis(
        "scope", "Có thể công ty đổi phần sở hữu ở công ty con",
        f"Nhiều dòng cùng đổi một lúc: phần lợi nhuận của cổ đông không kiểm soát {_move(mi.cur, mi.prev)}; "
        + "; ".join(signs) + ". Các dòng này thường cùng đổi khi công ty mua thêm, bán bớt, mất hoặc giành quyền "
        "kiểm soát một công ty con.",
        "Kiểm được bằng thuyết minh về các công ty con (danh sách và tỷ lệ sở hữu cuối kỳ so với đầu năm).",
        words="scope", sources=sources)


def one_off(f: Facts, notes: dict[str, list] | None = None) -> list[Hypothesis]:
    """Khoản ngoài hoạt động chính (thu nhập khác, doanh thu hoặc chi phí tài chính) chiếm phần lớn mức thay đổi LNTT,
    theo cả hai chiều."""
    if f.template in ("TCTD", "CTCK"):
        return []               # công ty chứng khoán: lãi vay, lãi tài sản tài chính là hoạt động chính (SSI quý 3/2026)
    pbt = _pair(f, "pbt")
    if pbt is None:
        return []
    cur, prev = pbt[0].value, pbt[1].value
    change = cur - prev
    if not change or (prev and abs(change) < abs(prev) * FLAT_PBT):
        return []
    out = []
    for metric in ("other_profit", "fin_income", "fin_expense"):
        expense = metric == "fin_expense"
        p = _pair(f, metric, LINE_CHECK[metric], expense=expense)
        if p is None:
            continue
        a, b = p[0].value, p[1].value
        effect = -(a - b) if expense else a - b
        if effect * change <= 0 or abs(effect) < abs(change) * ONE_OFF_OF_CHANGE \
                or abs(effect) < max(abs(cur), abs(prev)) * ONE_OFF_OF_PBT:
            continue
        if expense and (iv := _pair(f, "interest_expense", "lai vay", expense=True)) is not None \
                and abs(iv[0].value - iv[1].value) * 2 >= abs(a - b):
            continue            # chi phí tài chính đổi chủ yếu do lãi vay: khoản lặp lại, không phải một lần
        share = ("lớn hơn cả mức thay đổi LNTT" if abs(effect) > abs(change)
                 else f"bằng {vn(abs(effect) / abs(change) * 100, 0)}% mức {'tăng' if change > 0 else 'giảm'} LNTT")
        text = f"LNTT quý {_move(cur, prev)}; trong đó {LINE_NAMES[metric]} {_move(a, b)}, {share}. " + (
            "Đây là khoản ngoài hoạt động kinh doanh chính, thường không lặp lại đều đặn." if metric == "other_profit"
            else "Đây là khoản ngoài hoạt động kinh doanh chính (lãi tiền gửi, cổ tức, tỷ giá, chuyển nhượng khoản đầu "
                 "tư…); có thể có khoản một lần.")
        code = f.code("IS", metric)
        items = (notes or {}).get(code) or []
        if items:
            lab, x, y = max(items, key=lambda i: abs(i[1] - i[2]))
            text += f" Thuyết minh: khoản đổi nhiều nhất là \"{lab.strip()}\" ({_signed(y)} → {_signed(x)})."
        out.append(Hypothesis(
            "one_off", f"Có thể có khoản một lần ở {LINE_NAMES[metric]}", text,
            f"Kiểm được bằng thuyết minh của dòng {LINE_NAMES[metric]} và số các quý sau: khoản đó không còn thì đúng "
            "là một lần.", words="fin" if metric != "other_profit" else "other", sources=_src(*p, *pbt)))
    return out


def gross_split(f: Facts, bd) -> Hypothesis | None:
    """Lợi nhuận gộp là dòng đóng góp lớn nhất: tách mức đổi thành phần do doanh thu đổi (giữ biên cùng kỳ) và phần do
    biên lãi gộp đổi. Hai phần cộng đúng bằng mức đổi; đây là số tính được, không phải giả thuyết."""
    if f.template == "TCTD" or bd is None or not bd.ok or not bd.parts:
        return None
    top = max(bd.parts, key=lambda p: abs(p.effect))
    gp_code = f.code("IS", "gross_profit")
    if top.code != gp_code:
        return None
    rev, gp = _pair(f, "revenue"), _pair(f, "gross_profit")
    if rev is None or gp is None or rev[0].value <= 0 or rev[1].value <= 0:
        return None
    r1, r0, g1, g0 = rev[0].value, rev[1].value, gp[0].value, gp[1].value
    m0, m1 = g0 / r0, g1 / r1
    by_sales = (r1 - r0) * m0
    by_margin = (m1 - m0) * r1          # by_sales + by_margin = g1 − g0
    pct = lambda m: vn(m * 100)         # noqa: E731
    return Hypothesis(
        "gross", "Lợi nhuận gộp đổi do quy mô hay do biên",
        f"Lợi nhuận gộp quý {_move(g1, g0)}. Nếu giữ biên lãi gộp cùng kỳ ({pct(m0)}%), doanh thu thuần "
        f"{_move(r1, r0)} làm lợi nhuận gộp {'tăng' if by_sales >= 0 else 'giảm'} {ty(by_sales)}; biên lãi gộp "
        f"{'tăng' if m1 >= m0 else 'giảm'} từ {pct(m0)}% {'lên' if m1 >= m0 else 'xuống'} {pct(m1)}% làm lợi nhuận "
        f"gộp {'tăng' if by_margin >= 0 else 'giảm'} {ty(by_margin)}.",
        "Số tính từ doanh thu thuần và lợi nhuận gộp hai kỳ; vì sao doanh thu hoặc biên đổi thì cần thuyết minh doanh "
        "thu, giá vốn hoặc công văn.", label=COMPUTED, words="gross", sources=_src(*rev, *gp))


def bank_unusual(f: Facts, history: dict[str, dict[tuple[int, str], Decimal]], year: int, period: str) -> list[Hypothesis]:
    """Ngân hàng: thu dịch vụ, dự phòng hoặc lãi thuần hoạt động khác của quý cao hơn gấp đôi trung bình 4 quý trước
    của chính ngân hàng đó."""
    if f.template != "TCTD" or period not in QUARTERS:
        return []
    pbt = f.metric("IS", "pbt", "q_cur")
    before = _previous_quarters(year, period, 4)
    out = []
    for metric, (key, name) in BANK_LINES.items():
        cur = f.metric("IS", metric, "q_cur")
        known = [history.get(metric, {}).get(q) for q in before]
        known = [v for v in known if v is not None]
        if cur.value is None or len(known) < BANK_MIN_HISTORY:
            continue
        avg = sum(known) / len(known)
        if avg <= 0 or cur.value < avg * BANK_RATIO \
                or (pbt.value and cur.value - avg < abs(pbt.value) * BANK_MATERIAL):
            continue
        out.append(Hypothesis(
            "bank_unusual", f"{name[0].upper() + name[1:]} khác hẳn các quý trước",
            f"{name[0].upper() + name[1:]} quý này {ty(cur.value)}, gấp {vn(cur.value / avg)} lần trung bình "
            f"{len(known)} quý trước ({ty(avg)}). Có thể có khoản một lần hoặc khoản ghi nhận dồn vào quý này.",
            f"Kiểm được bằng thuyết minh của dòng {name} và số các quý sau.", words=key, sources=_src(cur)))
    return out


def _previous_quarters(year: int, period: str, n: int) -> list[tuple[int, str]]:
    i, y, out = QUARTERS.index(period), year, []
    for _ in range(n):
        i -= 1
        if i < 0:
            y, i = y - 1, 3
        out.append((y, QUARTERS[i]))
    return out


# ---------- công văn ----------

def attach_letter(hs: list[Hypothesis], reasons: list[str] | None) -> None:
    """Ghi công văn có nhắc tới ý của từng giả thuyết không (từ khóa trên lời công ty). None: chưa có công văn."""
    for h in hs:
        if reasons is None:
            h.company = "chưa có công văn"
            continue
        hit = next((r for r in reasons if re.search(WORDS.get(h.words, r"$^"), fold(r.lower()))), None)
        h.company = "công văn có nhắc tới" if hit else "công văn không nhắc tới"
        h.company_text = hit or ""


# ---------- lắp cho một BCTC ----------

def quarter_history(conn, ticker: str, scope: str, metrics) -> dict[str, dict[tuple[int, str], Decimal]]:
    """Giá trị quý của các chỉ tiêu từ các BCTC quý đã kiểm chứng hoặc đã duyệt (như npat_history)."""
    from services.metrics.service import _record
    rows = conn.execute(
        """SELECT id, fiscal_year, fiscal_period FROM documents
           WHERE ticker = %s AND scope = %s AND doc_type = 'fs_quarter' AND status IN ('verified', 'approved')
             AND content_kind = 'full' AND NOT is_amended AND owner_user_id IS NULL AND duplicate_of IS NULL
           ORDER BY fiscal_year, fiscal_period, source_listed_at""", (ticker, scope)).fetchall()
    own = {m: {} for m in metrics}
    prev = {m: {} for m in metrics}
    for doc_id, year, period in rows:
        rec = _record(conn, doc_id)
        if rec is None:
            continue
        f = Facts(doc_id, rec)
        if f.template is None:
            continue
        for m in metrics:
            if (v := f.metric("IS", m, "q_cur").value) is not None:
                own[m][(year, period)] = v
            if (v := f.metric("IS", m, "q_prev_year").value) is not None:
                prev[m][(year - 1, period)] = v
    return {m: prev[m] | own[m] for m in metrics}


def note_items(document_id: int) -> dict[str, list]:
    """Khoản con thuyết minh đã đọc và cộng khớp (riêng quý) theo mã dòng KQKD, từ kết quả agent nguyên nhân đã lưu."""
    path = raw_data_dir() / "causes" / f"{document_id}.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, list] = {}
    for g in data.get("gathered", []):
        if g.get("tool") == "note" and g.get("verified") and g.get("period") == "quarter" and g.get("items"):
            out.setdefault(g["line"], []).extend((lab, Decimal(a), Decimal(b)) for lab, a, b in g["items"])
    return out


def build(f: Facts, year: int, period: str, history=None, notes=None, reasons: list[str] | None = None) \
        -> list[Hypothesis]:
    st = f.statements.get("IS")
    if st is None or f.template is None:
        return []
    labels = {k: (f.rows[("IS", k)].label if ("IS", k) in f.rows else k) for k in st.values}
    bd = decompose_any(f.template, st.values, labels, f.flip_is, "quarter", st.multiplier * 20)
    hs = [h for h in (scope_change(f, bd), gross_split(f, bd)) if h is not None]
    hs += one_off(f, notes)
    hs += bank_unusual(f, history or {}, year, period)
    for h in hs:
        seen, uniq = set(), []
        for x in h.sources:
            if (key := (x.document_id, x.page, x.label)) not in seen:
                seen.add(key)
                uniq.append(x)
        h.sources = uniq
    attach_letter(hs, reasons)
    return hs


def for_document(conn, document_id: int, record: dict, letter=None) -> list[Hypothesis]:
    """Giả thuyết cho thẻ quý của một BCTC (0 USD). `letter`: kết quả services.metrics.service.explanation."""
    row = conn.execute("SELECT ticker, fiscal_year, fiscal_period, scope, doc_type FROM documents WHERE id = %s",
                       (document_id,)).fetchone()
    if row is None or row[4] != "fs_quarter":
        return []
    ticker, year, period, scope, _ = row
    f = Facts(document_id, record)
    history = quarter_history(conn, ticker, scope, list(BANK_LINES)) if f.template == "TCTD" else {}
    reasons = None
    if letter is not None and letter["view"].read:
        reasons = [r.text for r in letter["view"].reasons]
    return build(f, year, period, history, note_items(document_id), reasons)
