"""Sinh hình đồ thị LangGraph của agent báo cáo (so-do/agent-graph.tex) từ chính đồ thị đã biên dịch trong code.

    Code/.venv/Scripts/python Baocao/bao-cao-ky-thuat/tools/agent_graph.py

Nút và cạnh lấy từ `build(...).get_graph()`; vị trí, tên tiếng Việt và điều kiện của từng cạnh khai báo ở đây. Đồ thị
trong code có nút hay cạnh chưa khai báo (hoặc khai báo thừa) thì dừng với lỗi, để hình không lệch khỏi code.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "Code"))

from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from services.analyst.graph import build  # noqa: E402

# nút: (x, y, dòng mô tả); hai nút dừng chờ người dùng hoặc bộ canh có thêm nhãn «dừng chờ»
NODES = {
    "understand": (0, -1.5, "hiểu yêu cầu"),
    "inventory": (0, -3.6, "kiểm kho BCTC"),
    "confirm": (5.4, -3.6, "xin đọc thêm BCTC"),
    "wait": (10.2, -3.6, "chờ bộ canh đọc"),
    "compute": (0, -5.6, "tính bảng số"),
    "write": (0, -7.6, "viết lời (mô hình)"),
    "check": (0, -9.6, "kiểm từng câu"),
}
ENDS = (("eu", -1.5), ("ec", -5.6), ("ek", -9.6))      # mỗi nhánh kết thúc ở một nút cuối riêng (UML cho phép)
PAUSE = {"confirm", "wait"}

# cạnh: đường vẽ TikZ (dùng tên nút) và điều kiện; cạnh có điều kiện vẽ nét đứt
EDGES = {
    ("__start__", "understand"): ("(s) -- (understand)", ""),
    ("understand", "inventory"): ("(understand) -- node[left,guard]{[hợp lệ]} (inventory)", ""),
    ("understand", "__end__"): ("(understand.west) -- node[above,guard]{[thiếu mã, mã lạ]} (eu)", ""),
    ("inventory", "confirm"): ("(inventory) -- node[above,guard]{[thiếu BCTC]} (confirm)", ""),
    ("inventory", "compute"): ("(inventory) -- node[left,guard]{[đủ, hoặc đã hỏi]} (compute)", ""),
    ("confirm", "wait"): ("(confirm) -- node[above,guard]{[đồng ý]} (wait)", ""),
    ("confirm", "compute"): ("(confirm.south) |- node[pos=0.25,right,guard]{[không]} (compute.east)", ""),
    ("wait", "inventory"): ("(wait.north) -- ++(0,0.9) -| ($(inventory.north)+(1.0,0)$)", ""),
    ("compute", "write"): ("(compute) -- node[left,guard]{[có số]} (write)", ""),
    ("compute", "__end__"): ("(compute.west) -- node[above,guard,align=center]{[dùng lại,\\\\kho rỗng]} (ec)", ""),
    ("write", "write"): ("(write.east) -- ++(0.8,0) |- node[pos=0.25,right,guard,align=left]{[xin thêm số,\\\\tối đa 3 lần]}"
                         " ($(write.north)+(1.0,0)$)", ""),
    ("write", "check"): ("(write) -- node[left,guard]{[viết xong]} (check)", ""),
    ("check", "write"): ("(check.east) -- ++(3.4,0) |- node[pos=0.25,right,guard,align=left]{[còn câu sai,\\\\chưa quá 2 lần]} "
                         "($(write.east)+(0,-0.2)$)", ""),
    ("check", "__end__"): ("(check.west) -- node[above,guard,align=center]{[xong, hoặc\\\\hết lượt sửa]} (ek)", ""),
}


def tex() -> str:
    g = build(None, InMemorySaver()).get_graph()
    nodes = {n for n in g.nodes if not n.startswith("__")}
    edges = {(e.source, e.target): e.conditional for e in g.edges}
    if nodes != set(NODES):
        raise SystemExit(f"Nút trong code khác khai báo: thừa {nodes - set(NODES)}, thiếu {set(NODES) - nodes}")
    if set(edges) != set(EDGES):
        raise SystemExit(f"Cạnh trong code khác khai báo: thừa {set(edges) - set(EDGES)}, thiếu {set(EDGES) - set(edges)}")
    out = ["% Sinh tự động bởi tools/agent_graph.py từ đồ thị LangGraph trong code; đừng sửa tay.",
           r"\begin{tikzpicture}[font=\footnotesize\sffamily]",
           r"  \node[start] (s) at (0,0) {};"]
    for name, (x, y, label) in NODES.items():
        pause = r"\\{\scriptsize «dừng chờ»}" if name in PAUSE else ""
        out.append(rf"  \node[state,minimum width=30mm] ({name}) at ({x},{y}) {{\texttt{{{name}}}\\{label}{pause}}};")
    for name, y in ENDS:
        out.append(rf"  \node[stop] ({name}) at (-4.4,{y}) {{}};")
    for (src, tgt), (path, _) in EDGES.items():
        style = "flow,dashed" if edges[(src, tgt)] else "flow"
        out.append(rf"  \draw[{style}] {path};")
    out.append(r"\end{tikzpicture}")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    target = HERE.parent / "so-do" / "agent-graph.tex"
    target.write_text(tex(), encoding="utf-8")
    print(f"đã ghi {target}")
