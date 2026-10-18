from types import SimpleNamespace

from services.extraction import second_read


class FakeClient:
    def __init__(self, other):
        self.other, self.usage, self.last_model, self.calls = other, SimpleNamespace(usd=0.0), None, []

    def other_than(self, provider):
        return self.other

    def json_from_images(self, prompt, images, schema, name, step=None, detail=None, provider=None):
        self.calls.append((step, [label for label, _ in images], provider))
        self.usage.usd += 0.01
        self.last_model = f"{provider}-model"
        return {"rows": []}


RECORD = {"provider": "anthropic", "model": "haiku", "chosen": "a.pdf",
          "candidates": [{"name": "a.pdf", "statement_pages": {"BS": [3, 4], "IS": [5], "CF": [6]}, "rotations": {}}],
          "raw": {"BS": {"rows": [{"page": 4}, {"page": 5}]}, "IS": {"rows": []}, "CF": {"rows": []}}}


def test_reads_only_requested_statements_with_the_other_provider(monkeypatch):
    monkeypatch.setattr(second_read, "_extract_image", lambda doc, page, rotation: b"")
    monkeypatch.setattr(second_read, "_extract_detail", lambda doc, pages: None)
    client = FakeClient("openai")
    got = second_read.read(RECORD, client, doc=None, statements={"BS", "CF"})
    # trang BCĐKT gồm cả trang 5 mà lần đọc đầu đã chép dòng BCĐKT (bước định vị bỏ sót)
    assert client.calls == [("second_read_BS", ["Trang 3", "Trang 4", "Trang 5"], "openai"),
                            ("second_read_CF", ["Trang 6"], "openai")]
    assert set(got["raw"]) == {"BS", "CF"}
    assert got["second_reader"] == ["openai-model"] and round(got["usd"], 2) == 0.02


def test_no_second_reader_when_only_one_provider_is_configured():
    assert second_read.read(RECORD, FakeClient(None), doc=None) is None
