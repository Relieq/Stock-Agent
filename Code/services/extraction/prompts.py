"""Lời nhắc và JSON schema cho mô hình đọc ảnh BCTC.

Nguyên tắc: mô hình chỉ **định vị trang** và **chép lại nguyên văn** các ô trong bảng. Mọi việc đổi chuỗi thành số,
đổi đơn vị, kiểm tra cộng tổng đều làm bằng code (services/extraction/numbers.py, validate.py).
"""

from __future__ import annotations

PAGE_KINDS = [
    "cover", "letter", "management_report", "audit_or_review_report",
    "balance_sheet", "income_statement", "cash_flow", "equity_changes", "notes", "other",
]

STATEMENT_OF_KIND = {"balance_sheet": "BS", "income_statement": "IS", "cash_flow": "CF"}

COLUMN_KINDS = {
    "BS": ["end_period", "begin_year"],
    "IS": ["q_cur", "q_prev_year", "ytd_cur", "ytd_prev_year"],
    "CF": ["ytd_cur", "ytd_prev_year"],
}

_NULLABLE_STRING = {"type": ["string", "null"]}

LOCATE_SCHEMA = {
    "type": "object",
    "properties": {
        "pages": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "page": {"type": "integer"},
                    "kind": {"type": "string", "enum": PAGE_KINDS},
                    "language": {"type": "string", "enum": ["vi", "en", "other"]},
                    "rotation": {"type": "integer", "enum": [0, 90, 180, 270]},
                },
                "required": ["page", "kind", "language", "rotation"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["pages"],
    "additionalProperties": False,
}

LOCATE_PROMPT = """Đây là các trang đầu của một báo cáo tài chính doanh nghiệp Việt Nam (bản scan).
Mỗi ảnh có nhãn "Trang N" ngay trước nó. Với MỖI trang, cho biết:
- kind: loại trang, một trong:
  cover (trang bìa / mục lục), letter (công văn, giải trình), management_report (báo cáo của Ban Giám đốc / HĐQT),
  audit_or_review_report (báo cáo kiểm toán hoặc soát xét), balance_sheet (Bảng cân đối kế toán hoặc
  Báo cáo tình hình tài chính, kể cả các trang tiếp theo), income_statement (Báo cáo kết quả hoạt động kinh doanh),
  cash_flow (Báo cáo lưu chuyển tiền tệ), equity_changes (Báo cáo thay đổi vốn chủ sở hữu),
  notes (Thuyết minh báo cáo tài chính), other.
- language: ngôn ngữ chính của trang: vi, en hoặc other.
- rotation: số độ cần xoay ảnh THEO CHIỀU KIM ĐỒNG HỒ để chữ trên trang đứng thẳng, đọc được từ trái sang phải
  (0 nếu chữ đã thẳng; 90 nếu chữ đang chạy từ dưới lên; 270 nếu chữ đang chạy từ trên xuống; 180 nếu lộn ngược).
Trang bảng biểu kéo dài sang trang sau thì trang sau cũng mang cùng loại. Trả về đúng một phần tử cho mỗi trang."""


REREAD_SCHEMA = {
    "type": "object",
    "properties": {
        "cells": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "column_kind": {"type": "string"},
                    "value": _NULLABLE_STRING,
                },
                "required": ["code", "column_kind", "value"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["cells"],
    "additionalProperties": False,
}


def reread_prompt(statement: str, cells: list[tuple[str, str, str]]) -> str:
    """cells: (mã số, tên chỉ tiêu, column_kind). Cố ý không đưa con số mong đợi để mô hình không "sửa cho khớp"."""
    lines = "\n".join(f"- mã {code} ({label}), cột {col}" for code, label, col in cells)
    return f"""Ảnh sau là {_STATEMENT_NAME[statement]} trong một BCTC Việt Nam, chụp ở độ phân giải cao.
Lần đọc trước có thể đã chép sai một vài chữ số ở các ô dưới đây. Hãy đọc lại THẬT CẨN THẬN từng chữ số của
từng ô và chép NGUYÊN VĂN như in (giữ dấu chấm, dấu phẩy, dấu ngoặc). Không tính toán, không chỉnh để các dòng
cộng cho khớp: chỉ chép đúng những gì nhìn thấy.
{_COLUMN_HELP[statement]}
Các ô cần đọc lại:
{lines}"""


def extract_schema(statement: str) -> dict:
    kinds = COLUMN_KINDS[statement]
    return {
        "type": "object",
        "properties": {
            "unit_text": _NULLABLE_STRING,
            "columns": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "header": {"type": "string"},
                        "kind": {"type": "string", "enum": kinds + ["other"]},
                    },
                    "required": ["header", "kind"],
                    "additionalProperties": False,
                },
            },
            "rows": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "code": _NULLABLE_STRING,
                        "label": {"type": "string"},
                        "note": _NULLABLE_STRING,
                        "page": {"type": "integer"},
                        "values": {
                            "type": "object",
                            "properties": {k: _NULLABLE_STRING for k in kinds},
                            "required": kinds,
                            "additionalProperties": False,
                        },
                    },
                    "required": ["code", "label", "note", "page", "values"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["unit_text", "columns", "rows"],
        "additionalProperties": False,
    }


_COLUMN_HELP = {
    "BS": "end_period = số cuối kỳ (tại ngày kết thúc kỳ báo cáo); begin_year = số đầu năm (thường là 01/01).",
    "IS": ("q_cur = quý này năm nay; q_prev_year = quý này năm trước; ytd_cur = lũy kế từ đầu năm đến cuối quý này "
           "(năm nay); ytd_prev_year = lũy kế cùng kỳ năm trước. BCTC bán niên/năm chỉ có cột lũy kế thì để các cột "
           "quý là null."),
    "CF": "ytd_cur = lũy kế từ đầu năm đến cuối kỳ này (năm nay); ytd_prev_year = lũy kế cùng kỳ năm trước.",
}

_STATEMENT_NAME = {
    "BS": "Bảng cân đối kế toán / Báo cáo tình hình tài chính",
    "IS": "Báo cáo kết quả hoạt động kinh doanh",
    "CF": "Báo cáo lưu chuyển tiền tệ",
}


def extract_prompt(statement: str) -> str:
    return f"""Các ảnh sau là {_STATEMENT_NAME[statement]} trong một BCTC Việt Nam (bản scan). Mỗi ảnh có nhãn "Trang N".
Hãy CHÉP LẠI NGUYÊN VĂN bảng số, theo đúng thứ tự từ trên xuống, mỗi dòng chỉ tiêu một phần tử trong rows:
- code: mã số in ở cột "Mã số" (ví dụ "110", "01", "411a"); không có thì null. Không lấy số thuyết minh làm mã số.
- label: tên chỉ tiêu đúng như in.
- note: nội dung cột "Thuyết minh" (ví dụ "5", "V.1"); không có thì null.
- page: số trang N của ảnh chứa dòng đó.
- values: chuỗi số đúng như in trên giấy cho từng cột, GIỮ NGUYÊN dấu chấm, dấu phẩy, dấu ngoặc, dấu trừ.
  Không tính toán, không làm tròn, không đổi đơn vị, không tự điền số còn thiếu. Ô trống hoặc "-" thì null.
  {_COLUMN_HELP[statement]}
- columns: liệt kê tiêu đề các cột số như in và cột đó ứng với kind nào ("other" nếu không thuộc loại nào).
- unit_text: dòng ghi đơn vị tính như in (ví dụ "Đơn vị tính: VND"); không thấy thì null.
Bỏ qua các dòng chữ ký, ngày tháng, ghi chú cuối trang. Dòng tiêu đề nhóm không có số (ví dụ "A. TÀI SẢN NGẮN HẠN"
nếu không có số) vẫn giữ lại với values toàn null."""
