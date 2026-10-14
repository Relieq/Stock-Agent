"""Sinh sơ đồ CSDL (TikZ) cho báo cáo từ cấu trúc bảng thật trong PostgreSQL, để sơ đồ luôn khớp với code.

    python tools/erd.py          # chạy từ Baocao/bao-cao-ky-thuat; cần container soi-db đang chạy

Ký hiệu: mỗi bảng là một hộp (tên bảng, rồi các cột: khóa chính PK, khóa ngoại FK, kiểu dữ liệu rút gọn); mỗi khóa ngoại
là một đường nối, hai đầu ghi bội số theo UML (1 và 0..*; 0..1 khi khóa ngoại cho phép rỗng). Bảng thuộc sơ đồ khác vẽ
nét đứt, chỉ có tên. Ghi ra so-do/erd-bctc.tex và so-do/erd-nguoi-dung.tex.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "so-do"

TYPES = {"character varying": "varchar", "character": "char", "timestamp with time zone": "timestamptz",
         "integer": "int", "bigint": "bigint", "numeric": "numeric", "text": "text", "boolean": "bool",
         "jsonb": "jsonb", "real": "real"}

# Bố cục từng sơ đồ: bảng -> (x, y) góc trên-trái, đơn vị cm. Bảng không có cột thì vẽ dạng tham chiếu (nét đứt).
DIAGRAMS = {
    "erd-bctc": {
        "full": {"companies": (0, 0), "agm_plans": (0, -4.0), "documents": (5.4, 0),
                 "line_items": (10.8, 0), "document_files": (10.8, -6.2), "validations": (10.8, -9.6)},
        "stub": {"users": (6.3, -11.2)},
    },
    "erd-nguoi-dung": {
        "full": {"users": (5.4, 0), "sessions": (0, 0), "login_tokens": (0, -3.4), "watchlist": (10.8, 0),
                 "notifications": (10.8, -3.0), "processing_requests": (5.4, -4.4)},
        "stub": {"companies": (15.2, -0.3), "documents": (11.4, -7.4)},
    },
}


def psql(sql: str) -> list[list[str]]:
    out = subprocess.run(["docker", "exec", "soi-db", "psql", "-U", "soi", "-d", "soi", "-At", "-F", "\t", "-c", sql],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return [line.split("\t") for line in out.splitlines() if line]


def schema():
    cols: dict[str, list[tuple[str, str, bool]]] = {}
    for t, c, typ, nullable in psql(
            "SELECT table_name, column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"):
        cols.setdefault(t, []).append((c, TYPES.get(typ, typ), nullable == "YES"))
    pks = {(t, c) for t, c in psql(
        "SELECT tc.table_name, k.column_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage k ON k.constraint_name = tc.constraint_name "
        "WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = 'public'")}
    fks = [tuple(r) for r in psql(
        "SELECT tc.table_name, k.column_name, u.table_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage k ON k.constraint_name = tc.constraint_name "
        "JOIN information_schema.constraint_column_usage u ON u.constraint_name = tc.constraint_name "
        "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public' ORDER BY 1, 2")]
    return cols, pks, fks


def esc(s: str) -> str:
    return s.replace("_", r"\_")


def table_node(name: str, pos, cols, pks, fk_cols) -> str:
    rows = []
    for c, typ, _ in cols:
        tag = ",".join(t for t, on in (("PK", (name, c) in pks), ("FK", c in fk_cols)) if on)
        key = r"\textbf{" + esc(c) + "}" if "PK" in tag else esc(c)
        rows.append(f"{tag} & {key} & {{\\color{{soigray}}{typ}}}")
    body = r"\\ ".join(rows)
    return (f"\\node[erd] ({name}) at ({pos[0]},{pos[1]}) {{\\textbf{{{esc(name)}}}\\nodepart{{two}}"
            f"\\begin{{tabular}}{{@{{}}l@{{\\,}}l@{{\\;}}l@{{}}}}{body}\\end{{tabular}}}};")


def edge(child: str, col: str, parent: str, nullable: bool, nth: int) -> str:
    """Bội số theo UML: phía bảng con 0..*, phía bảng cha 1 (0..1 nếu khóa ngoại cho phép rỗng). Nhiều khóa ngoại giữa
    cùng hai bảng thì uốn cong để không chồng nhau; tên cột khóa ngoại ghi ở giữa đường."""
    many, one = "0..*", ("0..1" if nullable else "1")
    path = "--" if nth == 0 else f"to[bend {'left' if nth % 2 else 'right'}={18 * ((nth + 1) // 2)}]"
    return (f"\\draw[erdline] ({child}) {path} node[erdmult,pos=0.12]{{{many}}} node[erdmult,pos=0.88]{{{one}}} "
            f"node[erdfk,midway]{{{esc(col)}}} ({parent});")


def main() -> None:
    cols, pks, fks = schema()
    OUT.mkdir(exist_ok=True)
    for name, layout in DIAGRAMS.items():
        tables = set(layout["full"]) | set(layout["stub"])
        lines = ["% Sinh tự động bởi tools/erd.py từ CSDL thật; đừng sửa tay.", r"\begin{tikzpicture}"]
        for t, pos in layout["full"].items():
            fk_cols = {c for ct, c, _ in fks if ct == t}
            lines.append(table_node(t, pos, cols[t], pks, fk_cols))
        for t, pos in layout["stub"].items():
            lines.append(f"\\node[erdstub] ({t}) at ({pos[0]},{pos[1]}) {{\\textbf{{{esc(t)}}}}};")
        seen: dict[tuple[str, str], int] = {}
        for ct, c, pt in fks:
            if ct in layout["full"] and pt in tables:
                nullable = next(n for cc, _, n in cols[ct] if cc == c)
                nth = seen.get((ct, pt), 0)
                seen[(ct, pt)] = nth + 1
                lines.append(edge(ct, c, pt, nullable, nth))
        lines.append(r"\end{tikzpicture}")
        (OUT / f"{name}.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(name, "->", OUT / f"{name}.tex")


if __name__ == "__main__":
    main()
