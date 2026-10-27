"""Trang giới thiệu: đường dẫn công khai, danh sách video demo, tên tệp video an toàn."""
import json

from services.api.landing import demo_videos, is_public, video_file


def test_only_home_and_listed_prefixes_are_public():
    assert is_public("/") and is_public("/dang-nhap") and is_public("/video/the-kqkd.mp4")
    assert is_public("/chia-se/MCH/q3-2026") and is_public("/static/style.css")
    assert not is_public("/mua-bctc") and not is_public("/ma/MCH") and not is_public("/quan-tri")


def test_video_file_accepts_only_plain_names_in_the_demo_folder(tmp_path):
    (tmp_path / "the-kqkd.mp4").write_bytes(b"x")
    (tmp_path / "the-kqkd.jpg").write_bytes(b"x")
    assert video_file(tmp_path, "the-kqkd.mp4") == tmp_path / "the-kqkd.mp4"
    assert video_file(tmp_path, "the-kqkd.jpg") == tmp_path / "the-kqkd.jpg"
    for bad in ("../secret.mp4", "videos.json", "a.exe", "khong-co.mp4", "THE.mp4"):
        assert video_file(tmp_path, bad) is None


def test_demo_videos_split_into_user_and_behind_the_scenes_and_skip_missing_files(tmp_path):
    items = [{"slug": s, "title": s, "desc": "", "seconds": 30} for s in ("gioi-thieu", "the-kqkd", "duyet-tay", "mat-tich")]
    (tmp_path / "videos.json").write_text(json.dumps(items), encoding="utf-8")
    for s in ("gioi-thieu", "the-kqkd", "duyet-tay"):
        (tmp_path / f"{s}.mp4").write_bytes(b"x")
    v = demo_videos(tmp_path)
    assert [x["slug"] for x in v["user"]] == ["the-kqkd"]
    assert [x["slug"] for x in v["behind"]] == ["duyet-tay"]
    assert v["intro"]["slug"] == "gioi-thieu"
    assert demo_videos(tmp_path / "khong-co") == {"intro": None, "user": [], "behind": []}
