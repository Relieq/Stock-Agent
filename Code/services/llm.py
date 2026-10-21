"""Gọi mô hình ngôn ngữ / thị giác, có nhà cung cấp chính và nhà cung cấp dự phòng.

Cấu hình trong Code/.env (nguyên tắc "không khóa vào một nhà cung cấp", architecture.md mục 1):

    LLM_PROVIDER=...            # nhà cung cấp chính: anthropic / openai / gemini / openrouter / ollama / custom
    LLM_MODEL=...               # mô hình của nhà cung cấp chính; xem danh sách: python -m services.llm
    LLM_FALLBACK_PROVIDER=...   # tùy chọn: nhà cung cấp dự phòng
    LLM_FALLBACK_MODEL=...      # mô hình của nhà cung cấp dự phòng
    ANTHROPIC_API_KEY=... / OPENAI_API_KEY=... / GEMINI_API_KEY=... / OPENROUTER_API_KEY=... / LLM_API_KEY=...
    LLM_BASE_URL=...            # chỉ cần khi provider là custom
    LLM_REASONING_EFFORT=low    # mức suy nghĩ, dùng cho cả hai (OpenAI: reasoning_effort; Claude: output_config.effort)

Người quản trị có thể đảo nhà chính và nhà dự phòng trên web (trang Chi phí); lựa chọn lưu trong Data/raw/settings.json
để web, bộ canh và lệnh chạy tay cùng đọc. Khi nhà đang dùng báo hết tiền, bị giới hạn lượt, lỗi máy chủ, mất kết nối
hay sai khóa (sau khi thư viện đã tự thử lại), VisionClient chuyển sang nhà còn lại cho mọi lần gọi sau và ghi lại lần
chuyển (VisionClient.switches). Claude từ chối một yêu cầu thì chỉ lần gọi đó chuyển sang nhà dự phòng.

Anthropic gọi qua thư viện chính thức `anthropic`; các nhà cung cấp còn lại qua giao diện kiểu OpenAI.
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from services.db import CODE_DIR  # nạp Code/.env

PROVIDERS = {
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
    "openai": ("https://api.openai.com/v1", "OPENAI_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "ollama": ("http://localhost:11434/v1", None),
    "anthropic": ("https://api.anthropic.com", "ANTHROPIC_API_KEY"),
}


@dataclass
class LLMConfig:
    provider: str
    base_url: str
    api_key: str
    model: str | None


def _provider_config(provider: str, model: str | None) -> LLMConfig:
    provider = provider.lower()
    if provider == "custom":
        base_url, key_env = os.environ["LLM_BASE_URL"], "LLM_API_KEY"
    elif provider in PROVIDERS:
        base_url, key_env = PROVIDERS[provider]
    else:
        raise RuntimeError(f"Nhà cung cấp {provider!r} không hợp lệ ({' / '.join([*PROVIDERS, 'custom'])})")
    api_key = (os.environ.get(key_env) if key_env else None) or os.environ.get("LLM_API_KEY") or "none"
    if api_key == "none" and provider != "ollama":
        raise RuntimeError(f"Chưa có API key: đặt {key_env} trong Code/.env")
    return LLMConfig(provider, base_url, api_key, model)


def settings_path() -> Path:
    return (CODE_DIR / os.environ.get("RAW_DATA_DIR", "../Data/raw")).resolve() / "settings.json"


def read_settings() -> dict:
    try:
        return json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_settings(**changes) -> dict:
    data = read_settings() | changes
    path = settings_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return data


def configured() -> list[tuple[str, str | None]]:
    """(nhà cung cấp, mô hình) đã cấu hình trong .env: nhà chính rồi nhà dự phòng (nếu có)."""
    primary = (os.environ.get("LLM_PROVIDER") or "").lower()
    if not primary:
        raise RuntimeError("Chưa chọn nhà cung cấp mô hình: đặt LLM_PROVIDER trong Code/.env "
                           f"({' / '.join([*PROVIDERS, 'custom'])})")
    out = [(primary, os.environ.get("LLM_MODEL") or None)]
    fallback = (os.environ.get("LLM_FALLBACK_PROVIDER") or "").lower()
    if fallback and fallback != primary:
        out.append((fallback, os.environ.get("LLM_FALLBACK_MODEL") or None))
    return out


def provider_order() -> list[tuple[str, str | None]]:
    """Thứ tự dùng: nhà người quản trị chọn trên web (settings.json) đứng đầu, nếu nhà đó đã cấu hình."""
    order = configured()
    chosen = read_settings().get("llm_primary")
    return sorted(order, key=lambda pm: pm[0] != chosen) if any(p == chosen for p, _ in order) else order


def step_providers() -> dict[str, str]:
    """Bước nào luôn ưu tiên nhà cung cấp nào (tiền tố tên bước -> nhà cung cấp), bất kể nhà chính là ai. Ví dụ đo
    17/10/2026 trên 31 BCTC quý 2/2026: OpenAI định vị trang đúng góc xoay 31/31, Claude Haiku 5.5 chỉ 27/31, trong khi
    Haiku chép bảng đúng hơn; nên đặt page_classification=openai. Nguồn: trang Chi phí (settings.json), nếu chưa đặt thì
    LLM_STEP_PROVIDERS trong Code/.env (dạng "page_classification=openai,identify_upload=openai")."""
    chosen = read_settings().get("llm_step_providers")
    if isinstance(chosen, dict):
        return {k: v for k, v in chosen.items() if v}
    out = {}
    for part in (os.environ.get("LLM_STEP_PROVIDERS") or "").split(","):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip().lower()
    return out


def config() -> LLMConfig:
    """Cấu hình của nhà cung cấp đang đứng đầu."""
    provider, model = provider_order()[0]
    return _provider_config(provider, model)


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    usd: float = 0.0          # tính theo mô hình thực sự trả lời từng lần gọi (có thể khác nhau khi đã chuyển nhà)


# Giá công bố, USD cho 1 triệu token (vào, ra). OpenAI: bảng giá qua các trang tổng hợp, xem ngày 11/10/2026.
# Claude: bảng giá Anthropic, xem ngày 17/10/2026 (Haiku 5.5: giá cho lời nhắc tới 100 nghìn token; dài hơn là 0,50 /
# 2,50, Soi không gửi lời nhắc dài như vậy). Token ra gồm cả phần suy luận. Mô hình không có trong bảng thì không ước tính.
PRICES = {
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4": (2.50, 15.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}


# Trần token ra cho mỗi lần gọi, theo bước (tiền tố tên bước), để chặn câu trả lời dài bất thường. Đặt khoảng 3-4 lần
# mức lớn nhất đo được trên 120 BCTC quý 4/2025 - bán niên 2026 (trung bình mỗi lần gọi: chép báo cáo <= 5.700, đọc lại
# trang <= 4.150, định vị trang <= 1.300, đọc lại ô <= 1.200), vì token ra gồm cả phần suy luận. Bước lạ: không đặt trần.
OUTPUT_LIMITS = (
    ("statement_", 24_000),       # chép cả một báo cáo, có thể nhiều trang
    ("second_read_", 24_000),     # người đọc thứ hai chép lại cả một báo cáo (eval/second_read.py)
    ("reextract_", 16_000),       # chép lại một trang
    ("page_classification", 6_000),
    ("identify_upload", 3_000),
    ("explanation_read", 12_000),  # đọc công văn giải trình (services/analyst/explanations.py)
    ("plan_request", 3_000),       # hiểu yêu cầu của agent báo cáo (services/analyst/plan.py)
    ("write_report", 12_000),      # viết lời báo cáo (services/analyst/writer.py)
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


class ProviderUnavailable(RuntimeError):
    """Nhà cung cấp không trả lời được lần gọi này (hết tiền, giới hạn lượt, lỗi máy chủ, mất kết nối, sai khóa, từ
    chối). `sticky`: chuyển hẳn sang nhà dự phòng cho các lần gọi sau (trừ trường hợp chỉ một yêu cầu bị từ chối)."""

    def __init__(self, message: str, sticky: bool = True):
        super().__init__(message)
        self.sticky = sticky


def _unavailable(e: Exception) -> bool:
    """Lỗi mà nhà cung cấp còn lại có thể không gặp. Dùng chung cho thư viện openai và anthropic (cùng tên lớp lỗi,
    cùng thuộc tính status_code)."""
    status = getattr(e, "status_code", None)
    if status is None:
        return type(e).__name__ in ("APIConnectionError", "APITimeoutError")
    if status in (401, 402, 403, 408, 429) or status >= 500:
        return True
    return status == 400 and any(w in str(e).lower() for w in ("credit", "billing", "quota"))


class _OpenAICompatible:
    def __init__(self, cfg: LLMConfig):
        from openai import OpenAI
        self.cfg = cfg
        self.client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url, max_retries=4, timeout=300)

    def call(self, prompt, images, schema, schema_name, limit, detail) -> tuple[dict, int, int]:
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
        if limit is not None:
            extra["max_completion_tokens"] = limit
        resp = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[{"role": "user", "content": content}],
            response_format={"type": "json_schema", "json_schema": {"name": schema_name, "schema": schema, "strict": True}},
            **extra,
        )
        ti = (resp.usage.prompt_tokens or 0) if resp.usage else 0
        to = (resp.usage.completion_tokens or 0) if resp.usage else 0
        if resp.choices[0].finish_reason == "length":
            raise RuntimeError("Mô hình trả lời bị cắt do vượt giới hạn độ dài")
        return json.loads(resp.choices[0].message.content or ""), ti, to


# Giới hạn ảnh của Claude (đời 4.7 trở đi): cạnh dài 2576 điểm ảnh và 4784 ô 28x28; ảnh lớn hơn bị API tự thu nhỏ.
# Soi thu nhỏ trước bằng Lanczos để kiểm soát chất lượng (cùng lý do với sources.render_sharp).
CLAUDE_MAX_EDGE, CLAUDE_MAX_PATCHES = 2576, 4784


def fit_claude(png: bytes) -> bytes:
    from PIL import Image
    im = Image.open(io.BytesIO(png))
    w, h = im.size
    s = min(1.0, CLAUDE_MAX_EDGE / max(w, h))
    while math.ceil(w * s / 28) * math.ceil(h * s / 28) > CLAUDE_MAX_PATCHES:
        s *= 0.99
    if s >= 1.0:
        return png
    buf = io.BytesIO()
    im.resize((round(w * s), round(h * s)), Image.LANCZOS).save(buf, "PNG")
    return buf.getvalue()


class _Anthropic:
    def __init__(self, cfg: LLMConfig):
        import anthropic
        self.cfg = cfg
        self.client = anthropic.Anthropic(api_key=cfg.api_key, max_retries=4, timeout=600)

    def call(self, prompt, images, schema, schema_name, limit, detail) -> tuple[dict, int, int]:
        content: list[dict] = [{"type": "text", "text": prompt}]
        for label, png in images:
            content.append({"type": "text", "text": label})
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                        "data": base64.standard_b64encode(fit_claude(png)).decode()}})
        output_config: dict = {"format": {"type": "json_schema", "schema": schema}}
        if (effort := os.environ.get("LLM_REASONING_EFFORT")) in ("low", "medium", "high", "xhigh", "max"):
            output_config["effort"] = effort
        # Chế độ suy nghĩ luôn bật trên các mô hình Claude mới: token ra gồm cả phần suy nghĩ, nên trần rộng hơn OpenAI.
        # Dùng streaming để câu trả lời dài không chạm giới hạn thời gian của một yêu cầu thường.
        with self.client.messages.stream(model=self.cfg.model, max_tokens=max(16_000, 2 * (limit or 16_000)),
                                         messages=[{"role": "user", "content": content}],
                                         output_config=output_config) as stream:
            resp = stream.get_final_message()
        ti, to = resp.usage.input_tokens, resp.usage.output_tokens
        if resp.stop_reason == "refusal":
            raise ProviderUnavailable(f"Claude từ chối yêu cầu ({getattr(resp, 'stop_details', None)})", sticky=False)
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("Mô hình trả lời bị cắt do vượt giới hạn độ dài")
        return json.loads(next(b.text for b in resp.content if b.type == "text")), ti, to


def _backend(cfg: LLMConfig):
    return _Anthropic(cfg) if cfg.provider == "anthropic" else _OpenAICompatible(cfg)


class VisionClient:
    def __init__(self, cfg: LLMConfig | None = None):
        if cfg is not None:
            self._configs = [cfg]
        else:
            self._configs = [_provider_config(p, m) for p, m in provider_order()]
        for c in self._configs:
            if not c.model:
                raise RuntimeError(f"Chưa chọn mô hình cho {c.provider}: đặt LLM_MODEL / LLM_FALLBACK_MODEL trong "
                                   "Code/.env (xem danh sách: python -m services.llm)")
        self._backends: dict[int, object] = {}
        self.active = 0
        self.extras: set[int] = set()         # mô hình chỉ dùng cho một bước (step_providers dạng "nhà:mô hình")
        self.down: set[int] = set()           # nhà cung cấp đã hết tiền / lỗi trong đợt này: chỉ dùng khi không còn nhà nào khác
        self.step_providers = step_providers() if cfg is None else {}
        self.usage = Usage()
        self.steps: dict[str, Usage] = {}     # theo bước, khóa là schema_name (page_classification, statement_BS...)
        self.switches: list[dict] = []        # các lần chuyển nhà cung cấp (thời điểm, từ, sang, lý do)
        self.last_model: str | None = None    # mô hình đã trả lời lần gọi gần nhất ("nhà/mô hình")

    @property
    def cfg(self) -> LLMConfig:
        """Cấu hình của nhà cung cấp đang dùng (đổi khi đã chuyển sang nhà dự phòng)."""
        return self._configs[self.active]

    def _extra(self, spec: str) -> int:
        provider, model = spec.split(":", 1)
        for i, c in enumerate(self._configs):
            if c.provider == provider and c.model == model:
                return i
        self._configs.append(_provider_config(provider, model))
        self.extras.add(len(self._configs) - 1)
        return len(self._configs) - 1

    def _get(self, i: int):
        if i not in self._backends:
            self._backends[i] = _backend(self._configs[i])
        return self._backends[i]

    def other_than(self, provider: str | None) -> str | None:
        """Nhà cung cấp chính/dự phòng khác `provider` (khác hãng với lần đọc đầu), None nếu chỉ cấu hình một nhà."""
        return next((c.provider for i, c in enumerate(self._configs)
                     if i not in self.extras and c.provider != provider), None)

    def steps_snapshot(self) -> dict:
        return {k: asdict(v) for k, v in self.steps.items()}

    def json_from_images(self, prompt: str, images: list[tuple[str, bytes]], schema: dict, schema_name: str,
                         step: str | None = None, detail: str | None = None, provider: str | None = None) -> dict:
        """Gửi lời nhắc kèm các ảnh PNG (mỗi ảnh có nhãn), nhận về JSON theo schema. `step` để tính chi phí theo
        bước (mặc định là schema_name). `detail="original"`: API OpenAI không thu nhỏ ảnh (mặc định của gpt-5.4-mini
        thu cạnh dài về 2048 điểm ảnh); Claude và các nhà khác không nhận tham số này. `provider`: ưu tiên nhà này cho riêng
        lần gọi (lần đọc dùng để kết luận phải khác hãng với lần đọc đầu), thay cho cài đặt theo bước."""
        limit = output_limit(step or schema_name)
        name = step or schema_name
        wanted = provider or next((p for prefix, p in self.step_providers.items() if name.startswith(prefix)), None)
        main = [i for i in range(len(self._configs)) if i not in self.extras]
        if wanted and ":" in wanted:
            # "nhà cung cấp:mô hình" (ví dụ repair_escalate=anthropic:claude-opus-5-5): mô hình riêng cho bước này,
            # không dùng cho các bước khác; lỗi thì quay về thứ tự thường
            first = self._extra(wanted)
        else:
            first = next((i for i in main if self._configs[i].provider == wanted and i not in self.down), self.active)
        order = [first] + [i for i in main if i != first]
        order = [i for i in order if i not in self.down] + [i for i in order if i in self.down]
        last: Exception | None = None
        for n, i in enumerate(order):
            started = time.monotonic()
            try:
                data, ti, to = self._get(i).call(prompt, images, schema, schema_name, limit, detail)
            except Exception as e:
                sticky = getattr(e, "sticky", True)
                if not (isinstance(e, ProviderUnavailable) or _unavailable(e)) or n == len(order) - 1:
                    raise
                last = e
                nxt = order[n + 1]
                self.switches.append({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "step": step or schema_name,
                                      "from": f"{self._configs[i].provider}/{self._configs[i].model}",
                                      "to": f"{self._configs[nxt].provider}/{self._configs[nxt].model}",
                                      "sticky": sticky, "reason": repr(e)[:300]})
                print(f"[llm] {self.switches[-1]['from']} lỗi ({type(e).__name__}); chuyển sang {self.switches[-1]['to']}",
                      file=sys.stderr, flush=True)
                if sticky:
                    self.down.add(i)
                    if i == self.active and nxt not in self.extras:
                        self.active = nxt
                continue
            usd = cost_usd(self._configs[i].model, ti, to) or 0.0
            self.last_model = f"{self._configs[i].provider}/{self._configs[i].model}"
            step_usage = self.steps.setdefault(step or schema_name, Usage())
            for u in (self.usage, step_usage):
                u.calls += 1
                u.seconds += time.monotonic() - started
                u.input_tokens += ti
                u.output_tokens += to
                u.usd += usd
            return data
        raise last or RuntimeError("Không có nhà cung cấp nào trả lời được")


def main() -> None:
    """In cấu hình hiện tại (nhà chính, nhà dự phòng) và danh sách mô hình mỗi nhà cho phép dùng."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    for n, (provider, model) in enumerate(provider_order()):
        cfg = _provider_config(provider, model)
        print(f"{'Nhà chính' if n == 0 else 'Dự phòng'}: {cfg.provider}; mô hình đang chọn: {cfg.model or '(chưa chọn)'}")
        if cfg.provider == "anthropic":
            import anthropic
            ids = [m.id for m in anthropic.Anthropic(api_key=cfg.api_key).models.list()]
        else:
            from openai import OpenAI
            ids = [m.id for m in OpenAI(api_key=cfg.api_key, base_url=cfg.base_url).models.list()]
        for i in sorted(ids):
            print("  ", i)


if __name__ == "__main__":
    main()
