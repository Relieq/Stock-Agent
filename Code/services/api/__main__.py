"""Chạy giao diện web trên máy: python -m services.api [--port 8000], rồi mở http://127.0.0.1:8000"""

import argparse

import uvicorn


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m services.api")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true", help="Tự nạp lại khi sửa code")
    args = p.parse_args()
    uvicorn.run("services.api.app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
