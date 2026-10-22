import os

import pytest


@pytest.fixture(autouse=True)
def _no_ledger(monkeypatch):
    """Lần gọi mô hình giả trong kiểm thử không ghi vào sổ chi phí thật (Data/raw/llm_calls.jsonl)."""
    monkeypatch.setenv("LLM_LEDGER", os.devnull)
