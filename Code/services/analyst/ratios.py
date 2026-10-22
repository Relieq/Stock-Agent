"""Tỷ lệ cần số dư bình quân (ROE, NIM), tính bằng code từ số đã kiểm chứng — không đụng CSDL, không gọi mô hình.

Định nghĩa (dùng cho mọi loại công ty có chỉ tiêu này):

* **Quy năm.** Tử số là số của kỳ nhân hệ số quy năm: số riêng một quý × 4; lũy kế 3/6/9/12 tháng × 12/số tháng
  (quý 1 × 4, bán niên × 2, 9 tháng × 4/3, cả năm × 1). Không tính theo số ngày; không lấy tổng 4 quý gần nhất (kho mới
  có từ quý 4/2025 nên phần lớn mã chưa đủ 4 quý).
* **Bình quân.** Trung bình cộng số dư đầu kỳ và cuối kỳ trên BCĐKT (hai điểm):
  - riêng quý: cuối quý này (cột cuối kỳ) và cuối quý liền trước (cột cuối kỳ của BCTC quý trước; quý 1 thì cột đầu năm
    của chính BCTC này);
  - lũy kế: cột đầu năm và cột cuối kỳ của chính BCTC đó.
  Thiếu một trong hai số dư (chưa có BCTC quý trước, ô "cần xem ảnh", dòng không đọc được) thì tỷ lệ để trống, không
  thay bằng số dư một điểm. Bình quân không dương thì cũng để trống.
* **ROE** = LNST của cổ đông công ty mẹ (ngân hàng: của cổ đông ngân hàng mẹ) quy năm / vốn chủ sở hữu bình quân của cổ
  đông công ty mẹ × 100. Vốn của cổ đông công ty mẹ = tổng vốn chủ sở hữu − lợi ích cổ đông không kiểm soát:
  - doanh nghiệp (TT200, TT99) và công ty chứng khoán: dòng 400 trừ dòng lợi ích cổ đông không kiểm soát nằm trong phần
    vốn (mã 4xx có tên "không kiểm soát"/"thiểu số": 429 ở TT200/TT99, 418 ở BCTC SSI);
  - ngân hàng: tổng vốn chủ sở hữu (b.te) trừ lợi ích cổ đông không kiểm soát (b.mi) khi dòng này nằm trong vốn (tổng nợ
    + tổng vốn = tổng nguồn vốn); khi b.mi in riêng ngoài vốn (tổng nợ + vốn + b.mi = tổng nguồn vốn) thì b.te đã là
    phần của cổ đông ngân hàng mẹ; không xác định được dòng nào chứa dòng nào thì để trống.
  BCTC không có dòng lợi ích cổ đông không kiểm soát: dùng tổng vốn, trừ khi BCKQKD có tách phần không kiểm soát (dấu
  hiệu dòng đó bị đọc sót) thì để trống.
* **NIM** (chỉ ngân hàng) = thu nhập lãi thuần quy năm / tài sản sinh lãi bình quân × 100. Tài sản sinh lãi = tiền gửi
  tại NHNN + tiền gửi và cho vay các TCTD khác + chứng khoán kinh doanh + cho vay khách hàng + hoạt động mua nợ + chứng
  khoán đầu tư, lấy đúng số dòng mục như in (đã trừ dự phòng). Không tính tiền mặt, công cụ phái sinh, góp vốn đầu tư dài
  hạn. Chỗ còn hở: dùng số sau dự phòng (BCĐKT không in riêng số gộp ở dòng mục), và chứng khoán kinh doanh có cả cổ
  phiếu (không sinh lãi) — phần này thường nhỏ. Tiền gửi tại NHNN, tiền gửi và cho vay TCTD khác, cho vay khách hàng,
  chứng khoán đầu tư là bắt buộc (thiếu là để trống); chứng khoán kinh doanh và mua nợ không in thì tính 0.
* **Biên lợi nhuận gộp** (doanh nghiệp, đã có trong danh mục tỷ lệ, catalog.RATIOS) = lợi nhuận gộp / doanh thu thuần
  cùng kỳ × 100; không cần số dư nên có cả số cùng kỳ.

ROE và NIM chưa có số cùng kỳ năm trước: cần số dư của năm trước ở hai thời điểm mà BCTC kỳ này không in.
"""

from __future__ import annotations

from decimal import Decimal

# Tài sản sinh lãi của ngân hàng (mã chuẩn b.* của services/extraction/bank.py)
EARNING_REQUIRED = ("b.sbv", "b.interbank", "b.loans", "b.inv_sec")
EARNING_OPTIONAL = ("b.trading_sec", "b.debt_purchase")
MONTHS = {"Q1": 3, "Q2": 6, "H1": 6, "Q3": 9, "Q4": 12, "FY": 12}


def annual_factor(basis: str, period: str) -> Decimal:
    """Hệ số quy năm: riêng quý × 4; lũy kế × 12/số tháng."""
    if basis == "quarter":
        return Decimal(4)
    return Decimal(12) / Decimal(MONTHS[period])


def average(begin: Decimal | None, end: Decimal | None) -> Decimal | None:
    if begin is None or end is None:
        return None
    return (begin + end) / 2


def annualised_ratio(num: Decimal | None, begin: Decimal | None, end: Decimal | None, factor: Decimal
                     ) -> Decimal | None:
    """Tử số quy năm / bình quân hai số dư × 100 (%). Thiếu số hoặc bình quân không dương: None."""
    avg = average(begin, end)
    if num is None or avg is None or avg <= 0:
        return None
    return num * factor / avg * 100


def _get(values: dict[str, Decimal], blocked: set[str], code: str):
    """(có dòng, giá trị); ô bị chặn (cần xem lại, thiếu dòng) thì ném KeyError để cả tỷ lệ để trống."""
    if code in blocked:
        raise KeyError(code)
    v = values.get(code)
    return v is not None, v


def earning_assets(values: dict[str, Decimal], blocked: set[str]) -> Decimal | None:
    """Tài sản sinh lãi của ngân hàng tại một thời điểm (một cột BCĐKT). `values`: mã -> số; `blocked`: mã có ô "cần xem
    lại" hoặc có dấu hiệu thiếu dòng ở cột này."""
    try:
        total = Decimal(0)
        for code in EARNING_REQUIRED:
            has, v = _get(values, blocked, code)
            if not has:
                return None
            total += v
        for code in EARNING_OPTIONAL:
            has, v = _get(values, blocked, code)
            total += v if has else 0
        return total
    except KeyError:
        return None


# Các khoản nợ của ngân hàng: cộng lại thay tổng nợ phải trả khi BCTC không in dòng tổng (như quy tắc BS_bank_tle_items)
BANK_LIABILITIES = ("b.gov", "b.interbank_liab", "b.cust_dep", "b.deriv_liab", "b.trust_funds", "b.papers",
                    "b.other_liab")
TOLERANCE = Decimal("0.000001")     # sai lệch làm tròn cho phép khi so tổng nguồn vốn (một phần triệu)


def parent_equity_bank(values: dict[str, Decimal], blocked: set[str]) -> Decimal | None:
    """Vốn chủ sở hữu của cổ đông ngân hàng mẹ tại một thời điểm (xem đầu file). Không in tổng nợ phải trả thì cộng các
    khoản nợ."""
    try:
        has_te, te = _get(values, blocked, "b.te")
        has_mi, mi = _get(values, blocked, "b.mi")
        if not has_te:
            return None
        if not has_mi or not mi:
            return te
        has_tle, tle = _get(values, blocked, "b.tle")
        has_tl, tl = _get(values, blocked, "b.tl")
        if not has_tl:
            parts = [_get(values, blocked, c) for c in BANK_LIABILITIES]
            has_tl = any(h for h, _ in parts)
            tl = sum((v for h, v in parts if h), Decimal(0))
    except KeyError:
        return None
    if not (has_tl and has_tle):
        return None
    mi = abs(mi)
    tol = abs(tle) * TOLERANCE
    inside, outside = abs(tl + te - tle), abs(tl + te + mi - tle)
    if inside <= tol and inside < outside:      # lợi ích không kiểm soát nằm trong tổng vốn
        return te - mi
    if outside <= tol and outside < inside:     # in riêng ngoài vốn: tổng vốn đã là phần của cổ đông mẹ
        return te
    return None


def parent_equity_corporate(values: dict[str, Decimal], blocked: set[str], minority_code: str | None,
                            split_in_is: bool) -> Decimal | None:
    """Vốn chủ sở hữu của cổ đông công ty mẹ (doanh nghiệp, công ty chứng khoán): dòng 400 trừ dòng lợi ích cổ đông
    không kiểm soát trong phần vốn. Không có dòng đó mà BCKQKD có tách phần không kiểm soát: None (đọc sót)."""
    try:
        has_eq, eq = _get(values, blocked, "400")
        if not has_eq:
            return None
        if minority_code is None:
            return None if split_in_is else eq
        has_mi, mi = _get(values, blocked, minority_code)
    except KeyError:
        return None
    if not has_mi:
        return None if split_in_is else eq
    return eq - mi
