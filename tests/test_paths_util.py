"""Тесты recorder.paths_util (валидация путей и имён)."""

from __future__ import annotations

from pathlib import Path

import pytest

from recorder import paths_util


def test_validate_stream_url_ok():
    assert paths_util.validate_stream_url("https://example.com/live.m3u8").startswith(
        "https://"
    )


def test_validate_stream_url_strips_invisible_copy_paste():
    raw = "\ufeffhttps://example.com/a.m3u8\u200b"
    assert paths_util.validate_stream_url(raw) == "https://example.com/a.m3u8"


@pytest.mark.parametrize(
    "bad",
    ["", "ftp://x", "/local/path.m3u8", "example.com/x.m3u8"],
)
def test_validate_stream_url_rejects(bad):
    with pytest.raises(ValueError, match="http"):
        paths_util.validate_stream_url(bad)


def test_validate_basename_ok():
    assert paths_util.validate_basename("steam1") == "steam1"
    assert paths_util.validate_basename("a_z-09") == "a_z-09"


@pytest.mark.parametrize(
    "bad",
    ["", " ", "рус", "has space", "a" * 81, "dot.mp4"],
)
def test_validate_basename_rejects(bad):
    with pytest.raises(ValueError, match="Имя файла"):
        paths_util.validate_basename(bad)


def test_normalize_basename_legacy_collisions():
    assert (
        paths_util.normalize_basename_legacy_collisions(
            paths_util.validate_basename("recording001001")
        )
        == "recording"
    )
    assert (
        paths_util.normalize_basename_legacy_collisions(
            paths_util.validate_basename("steam1")
        )
        == "steam1"
    )


def test_sanitize_subpath_ok():
    p = paths_util.sanitize_subpath("nas/show1")
    assert p == Path("nas") / "show1"


def test_sanitize_subpath_rejects_traversal():
    with pytest.raises(ValueError, match="Запрещён"):
        paths_util.sanitize_subpath("a/../../etc")


def test_allocate_unique_starting_part(tmp_path):
    root = tmp_path / "rec"
    root.mkdir()
    mode = 1
    sub = None
    assert paths_util.allocate_unique_starting_part(root, mode, sub, "x") == 1
    p1 = paths_util.output_mp4_path(root, mode, sub, "x", 1)
    p1.write_bytes(b"x")
    assert paths_util.allocate_unique_starting_part(root, mode, sub, "x") == 2


def test_allocate_unique_reuses_part_if_file_is_zero_bytes(tmp_path):
    root = tmp_path / "rec"
    root.mkdir()
    p1 = paths_util.output_mp4_path(root, 1, None, "y", 1)
    p1.write_bytes(b"")
    assert paths_util.allocate_unique_starting_part(root, 1, None, "y") == 1
    assert not p1.is_file()


def test_allocate_unique_starting_part_mode_2b(tmp_path):
    root = tmp_path / "rec"
    root.mkdir()
    sub = "nas"
    paths_util.output_mp4_path(root, 2, sub, "show", 1).write_bytes(b"a")
    assert paths_util.allocate_unique_starting_part(root, 2, sub, "show") == 2


def test_resolve_mp4_under_recordings_root_absolute(tmp_path):
    root = tmp_path / "rec"
    root.mkdir()
    f = root / "a_001.mp4"
    f.write_bytes(b"ab")
    abs_str = str(f.resolve())
    cand = paths_util.resolve_mp4_under_recordings_root(root, abs_str)
    assert cand.resolve() == f.resolve()


def test_resolve_existing_mp4(tmp_path):
    root = tmp_path / "rec"
    root.mkdir()
    f = root / "a_001.mp4"
    f.write_bytes(b"x")
    got = paths_util.resolve_existing_mp4(root, "a_001.mp4")
    assert got.resolve() == f.resolve()


def test_resolve_existing_mp4_rejects_traversal(tmp_path):
    root = tmp_path / "rec"
    root.mkdir()
    with pytest.raises(ValueError):
        paths_util.resolve_existing_mp4(root, "../evil.mp4")


def test_relative_to_recordings(tmp_path):
    root = tmp_path / "rec"
    root.mkdir()
    f = root / "sub" / "f.mp4"
    f.parent.mkdir(parents=True)
    f.touch()
    rel = paths_util.relative_to_recordings(root, f)
    assert rel.replace("\\", "/") == "sub/f.mp4"
