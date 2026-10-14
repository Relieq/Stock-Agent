"""Gọi mô hình ngôn ngữ / thị giác qua giao diện kiểu OpenAI.

Gemini, OpenAI, OpenRouter và Ollama đều có endpoint tương thích, nên đổi nhà cung cấp chỉ là đổi cấu hình
trong Code/.env (nguyên tắc "không khóa vào một nhà cung cấp", architecture.md mục 1):

    LLM_PROVIDER=...           # bắt buộc: gemini / openai / openrouter / ollama / custom
    OPENAI_API_KEY=...         # key tương ứng: GEMINI_API_KEY / OPENAI_API_KEY / OPENROUTER_API_KEY / LLM_API_KEY
    LLM_MODEL=...              # bắt buộc; xem danh sách mô hình dùng được: python -m services.llm
    LLM_BASE_URL=...           # chỉ cần khi LLM_PROVIDER=custom

Không có nhà cung cấp hay mô hình mặc định: lựa chọn này do người dùng quyết định sau khi so sánh.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from dataclasses import asdict, dataclass

from openai import OpenAI

import services.db  # noqa: F401  (nạp Code/.env)

PROVIDERS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
}


@dataclass
class LLMConfig:
    provider: str
    base_url: str
    api_key: str
    model: str | None


def config() -> LLMConfig:
    provider = (os.environ.get("LLM_PROVIDER") or "").lower()
    if not provider:
        raise RuntimeError("Chưa chọn nhà cung cấp mô hình: đặt LLM_PROVIDER trong Code/.env "
                           f"({' / '.join([*PROVIDERS, 'custom'])})")
    if provider == "custom":
        base_url, key_env = os.environ["LLM_BASE_URL"], "LLM_API_KEY"
    elif provider in PROVIDERS:
        base_url, key_env = PROVIDERS[provider]
    else:
        raise RuntimeError(f"LLM_PROVIDER={provider!r} không hợp lệ")
    api_key = os.environ.get("LLM_API_KEY") or (os.environ.get(key_env) if key_env else None) or "none"
    if api_key == "none" and provider != "ollama":
        raise RuntimeError(f"Chưa có API key: đặt {key_env} trong Code/.env")
    return LLMConfig(provider, base_url, api_key, os.environ.get("LLM_MODEL") or None)


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0


# Giá công bố, USD cho 1 triệu token (vào, ra). Nguồn: bảng giá OpenAI qua các trang tổng hợp, xem ngày 11/10/2026.
# Token ra gồm cả phần suy luận của mô hình. Mô hình không có trong bảng thì không ước tính chi phí.
PRICES = {
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4": (2.50, 15.00),
}


# Trần token ra cho mỗi lần gọi, theo bước (tiền tố tên bước), để chặn câu trả lời dài bất thường. Đặt khoảng 3-4 lần
# mức lớn nhất đo được trên 120 BCTC quý 4/2025 - bán niên 2026 (trung bình mỗi lần gọi: chép báo cáo <= 5.700, đọc lại
# trang <= 4.150, định vị trang <= 1.300, đọc lại ô <= 1.200), vì token ra gồm cả phần suy luận. Bước lạ: không đặt trần.
OUTPUT_LIMITS = (
    ("statement_", 24_000),       # chép cả một báo cáo, có thể nhiều trang
    ("reextract_", 16_000),       # chép lại một trang
    ("page_classification", 6_000),
    ("identify_upload", 3_000),
    ("verify_cells", 6_000), ("reread_cells", 6_000), ("repair_", 6_000),
)


def output_limit(step: str) -> int | None:
    return next((n for prefix, n in OUTPUT_LIMITS if step.startswith(prefix)), None)


def cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float | None:
    price = PRICES.get(model or "")
    if price is None:
        return None
    return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000


def usage_delta(after: dict, before: dict) -> dict:
    """Phần chênh của usage theo bước (dict bước -> dict Usage) giữa hai thời điểm."""
    out = {}
    for step, u in after.items():
        b = before.get(step, {})
        d = {k: v - b.get(k, 0) for k, v in u.items()}
        if d["calls"]:
            out[step] = d
    return out


class VisionClient:
    def __init__(self, cfg: LLMConfig | None = None):
        self.cfg = cfg or config()
        if not self.cfg.model:
            raise RuntimeError("Chưa chọn mô hình: đặt LLM_MODEL trong Code/.env (xem danh sách: python -m services.llm)")
        self.client = OpenAI(api_key=self.cfg.api_key, base_url=self.cfg.base_url, max_retries=4, timeout=300)
        self.usage = Usage()
        self.steps: dict[str, Usage] = {}     # theo bước, khóa là schema_name (page_classification, statement_BS...)

    def steps_snapshot(self) -> dict:
        return {k: asdict(v) for k, v in self.steps.items()}

    def json_from_images(self, prompt: str, images: list[tuple[str, bytes]], schema: dict, schema_name: str,
                         step: str | None = None, detail: str | None = None) -> dict:
        """Gửi lời nhắc kèm các ảnh PNG (mỗi ảnh có nhãn), nhận về JSON theo schema. `step` để tính chi phí theo
        bước (mặc định là schema_name). `detail="original"`: API OpenAI không thu nhỏ ảnh (mặc định của gpt-5.4-mini
        thu cạnh dài về 2048 điểm ảnh); nhà cung cấp khác không nhận tham số này nên bỏ qua."""
        content: list[dict] = [{"type": "text", "text": prompt}]
        for label, png in images:
            image_url = {"url": "data:image/png;base64," + base64.b64encode(png).decode()}
            if detail and self.cfg.provider == "openai":
                image_url["detail"] = detail
            content.append({"type": "text", "text": label})
            content.append({"type": "image_url", "image_url": image_url})
        # Một số mô hình (ví dụ dòng suy luận) không nhận temperature; chỉ gửi các tham số được cấu hình
        extra: dict = {}
        if os.environ.get("LLM_TEMPERATURE"):
            extra["temperature"] = float(os.environ["LLM_TEMPERATURE"])
        if os.environ.get("LLM_REASONING_EFFORT"):
            extra["reasoning_effort"] = os.environ["LLM_REASONING_EFFORT"]
        if (limit := output_limit(step or schema_name)) is not None:
            extra["max_completion_tokens"] = limit
        started = time.monotonic()
        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema, "strict": True}},
            **extra,
        )
        step_usage = self.steps.setdefault(step or schema_name, Usage())
        for u in (self.usage, step_usage):
            u.calls += 1
            u.seconds += time.monotonic() - started
            if resp.usage:
                u.input_tokens += resp.usage.prompt_tokens or 0
                u.output_tokens += resp.usage.completion_tokens or 0
        text = resp.choices[0].message.content or ""
        if resp.choices[0].finish_reason == "length":
            raise RuntimeError("Mô hình trả lời bị cắt do vượt giới hạn độ dài")
        return json.loads(text)


def main() -> None:
    """In cấu hình hiện tại và danh sách mô hình nhà cung cấp cho phép dùng."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    cfg = config()
    print(f"Nhà cung cấp: {cfg.provider} ({cfg.base_url}); mô hình đang chọn: {cfg.model or '(chưa chọn)'}")
    client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)
    for m in sorted(client.models.list(), key=lambda m: m.id):
        print("  ", m.id)


if __name__ == "__main__":
    main()
