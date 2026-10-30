import json
import os

from app.helpers.processed_media_store import (
    ProcessedMediaStore,
    match_outputs_to_sources,
    normalize_media_key,
)


def _media(tmp_path, name="clip.mp4", data=b"abc"):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_mark_persist_and_reload(tmp_path):
    media = _media(tmp_path)
    store_path = tmp_path / "store.json"
    store = ProcessedMediaStore(store_path)
    assert not store.is_processed(media)
    assert store.mark_processed(
        media, str(tmp_path / "out" / "clip_2026_01_01_00_00_00.mp4")
    )
    assert store.is_processed(media)

    reloaded = ProcessedMediaStore(store_path)
    assert reloaded.is_processed(media)
    assert len(reloaded) == 1
    assert reloaded.outputs_for(media)[0].endswith("clip_2026_01_01_00_00_00.mp4")
    assert json.loads(store_path.read_text())["version"] == 1


def test_changed_file_is_no_longer_processed(tmp_path):
    media = _media(tmp_path)
    store = ProcessedMediaStore(tmp_path / "store.json")
    store.mark_processed(media)
    with open(media, "ab") as fh:
        fh.write(b"more data")
    assert not store.is_processed(media)


def test_unmark_and_missing_file(tmp_path):
    media = _media(tmp_path)
    store = ProcessedMediaStore(tmp_path / "store.json")
    store.mark_processed(media)
    assert store.unmark(media)
    assert not store.is_processed(media)
    assert not store.unmark(media)
    assert not store.mark_processed(str(tmp_path / "missing.mp4"))


def test_corrupt_store_is_ignored(tmp_path):
    store_path = tmp_path / "store.json"
    store_path.write_text("{not json")
    store = ProcessedMediaStore(store_path)
    assert len(store) == 0
    store.mark_processed(_media(tmp_path))
    assert len(ProcessedMediaStore(store_path)) == 1


def test_normalize_media_key_is_absolute(tmp_path):
    rel = os.path.relpath(str(tmp_path / "a.mp4"))
    assert normalize_media_key(rel) == normalize_media_key(str(tmp_path / "a.mp4"))


def test_match_outputs_to_sources():
    sources = ["/in/holiday.mp4", "/in/holiday 2.mp4", "/in/pic.png"]
    outputs = [
        "/out/holiday_2026_10_30_12_00_00.mp4",
        "/out/holiday 2_2026_10_30_12_05_00.mp4",
        "/out/holiday_extra_2026_10_30_12_00_00.mp4",
        "/out/pic_2026_10_30_12_00_00.png",
        "/out/pic_2026_10_30_12_00_00.txt",
        "/out/custom-job-name.mp4",
    ]
    matches = match_outputs_to_sources(sources, outputs)
    assert matches["/in/holiday.mp4"] == ["/out/holiday_2026_10_30_12_00_00.mp4"]
    assert matches["/in/holiday 2.mp4"] == ["/out/holiday 2_2026_10_30_12_05_00.mp4"]
    assert matches["/in/pic.png"] == ["/out/pic_2026_10_30_12_00_00.png"]
