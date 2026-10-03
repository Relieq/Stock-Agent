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
from dataclasses import dataclass

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


class VisionClient:
    def __init__(self, cfg: LLMConfig | None = None):
        self.cfg = cfg or config()
        if not self.cfg.model:
            raise RuntimeError("Chưa chọn mô hình: đặt LLM_MODEL trong Code/.env (xem danh sách: python -m services.llm)")
        self.client = OpenAI(api_key=self.cfg.api_key, base_url=self.cfg.base_url, max_retries=4, timeout=300)
        self.usage = Usage()

    def json_from_images(self, prompt: str, images: list[tuple[str, bytes]], schema: dict, schema_name: str) -> dict:
        """Gửi lời nhắc kèm các ảnh PNG (mỗi ảnh có nhãn), nhận về JSON theo schema."""
        content: list[dict] = [{"type": "text", "text": prompt}]
        for label, png in images:
            content.append({"type": "text", "text": label})
            content.append({
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()},
            })
        # Một số mô hình (ví dụ dòng suy luận) không nhận temperature; chỉ gửi các tham số được cấu hình
        extra: dict = {}
        if os.environ.get("LLM_TEMPERATURE"):
            extra["temperature"] = float(os.environ["LLM_TEMPERATURE"])
        if os.environ.get("LLM_REASONING_EFFORT"):
            extra["reasoning_effort"] = os.environ["LLM_REASONING_EFFORT"]
        started = time.monotonic()
        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema, "strict": True}},
            **extra,
        )
        self.usage.calls += 1
        self.usage.seconds += time.monotonic() - started
        if resp.usage:
            self.usage.input_tokens += resp.usage.prompt_tokens or 0
            self.usage.output_tokens += resp.usage.completion_tokens or 0
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
