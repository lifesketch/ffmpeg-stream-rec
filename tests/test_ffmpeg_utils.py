"""Smoke-тесты сборки аргументов FFmpeg/ffprobe."""

from __future__ import annotations

from pathlib import Path

from recorder import ffmpeg_utils


def test_build_record_args_contains_io(tmp_path):
    out = tmp_path / "o.mp4"
    args = ffmpeg_utils.build_record_args("ffmpeg", "https://x/y.m3u8", out)
    assert args[0] == "ffmpeg"
    assert "https://x/y.m3u8" in args
    assert str(out) in args
    assert "-c" in args and "copy" in args
    assert "-nostats" in args
    assert "-loglevel" in args and "warning" in args
    assert "-flush_packets" in args
    assert "-movflags" in args
    assert any("frag_keyframe" in str(a) for a in args)


def test_build_integrity_check_args(tmp_path):
    f = tmp_path / "a.mp4"
    f.write_bytes(b"x")
    args = ffmpeg_utils.build_integrity_check_args("ffmpeg", f)
    assert "-v" in args and "error" in args
