"""Срез stderr FFmpeg для логов."""
from recorder.service import _ffmpeg_stderr_tail_for_diagnostics


def test_stderr_tail_prefers_error_after_long_banner() -> None:
    banner = "x" * 12000 + "ffmpeg version 5\n" + "configuration: " + "y" * 8000
    err = "\nInvalid data found when processing input\n"
    raw = (banner + err).encode()
    t = _ffmpeg_stderr_tail_for_diagnostics(raw)
    assert "Invalid data found" in t
    assert "configuration:" not in t or "Invalid" in t


def test_stderr_tail_short_output_unchanged() -> None:
    s = "hello\nworld\n"
    assert _ffmpeg_stderr_tail_for_diagnostics(s.encode()) == s.rstrip("\n") + "\n"
