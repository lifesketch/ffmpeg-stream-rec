"""Порог «пустого» MP4 при code=0 от FFmpeg."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from recorder.service import RecordingService


@pytest.fixture
def svc(tmp_path):
    root = tmp_path / "rec"
    root.mkdir()
    logd = tmp_path / "logs"
    logd.mkdir()
    return RecordingService(
        {
            "RECORDINGS_ROOT": str(root),
            "LOG_DIR": str(logd),
            "MAX_INDEPENDENT_SESSIONS": 2,
            "MAX_CONTINUATIONS": 3,
            "FFMPEG_BIN": "ffmpeg",
            "RECORDING_SHUTDOWN_WAIT_SEC": 1.0,
        },
        MagicMock(),
        MagicMock(),
    )


def test_part_too_small_missing_file(svc):
    row = SimpleNamespace(current_output_path="none_001.mp4")
    assert svc._part_file_too_small_for_graceful_complete(row) is True


def test_part_too_small_tiny_file(svc):
    root = Path(svc._cfg["RECORDINGS_ROOT"])
    p = root / "x_001.mp4"
    p.write_bytes(b"\x00" * 100)
    row = SimpleNamespace(current_output_path="x_001.mp4")
    assert svc._part_file_too_small_for_graceful_complete(row) is True


def test_part_big_enough(svc):
    root = Path(svc._cfg["RECORDINGS_ROOT"])
    p = root / "y_001.mp4"
    p.write_bytes(b"\x00" * 5000)
    row = SimpleNamespace(current_output_path="y_001.mp4")
    assert svc._part_file_too_small_for_graceful_complete(row) is False
