"""Юнит-тесты RecordingService (без реального FFmpeg, Popen замокан)."""

from __future__ import annotations

import logging
import uuid
from unittest.mock import MagicMock

import pytest

from recorder.service import RecordingService
from recorder.store import SessionStore


@pytest.fixture
def recording_svc(tmp_path, monkeypatch):
    rec = tmp_path / "recordings"
    rec.mkdir(parents=True)
    db = tmp_path / "state.sqlite3"
    store = SessionStore(db)
    store.init_db()
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)

    def fake_popen(*_a, **_kw):
        proc = MagicMock()
        proc.pid = 900_000 + hash(uuid.uuid4()) % 1000
        proc.poll.return_value = None
        proc.stderr = None
        proc.wait.return_value = 0
        return proc

    monkeypatch.setattr("recorder.service.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "recorder.service.RecordingService._watch_popen",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "recorder.service.process_utils.graceful_terminate",
        lambda *a, **k: None,
    )

    cfg = {
        "RECORDINGS_ROOT": rec,
        "STATE_DB_PATH": db,
        "LOG_DIR": tmp_path / "logs",
        "MAX_INDEPENDENT_SESSIONS": 2,
        "MAX_CONTINUATIONS": 3,
        "FFMPEG_BIN": "ffmpeg",
        "FFPROBE_BIN": "ffprobe",
        "DEFAULT_RECORDING_BASENAME": "steam1",
    }
    log = logging.getLogger("pytest-recording-svc")
    log.addHandler(logging.NullHandler())
    return RecordingService(cfg, store, log)


def test_start_recording_raises_when_session_limit(recording_svc: RecordingService):
    recording_svc.start_recording(
        stream_url="https://a.com/1.m3u8",
        storage_mode=1,
        subpath=None,
        basename="u1",
    )
    recording_svc.start_recording(
        stream_url="https://a.com/2.m3u8",
        storage_mode=1,
        subpath=None,
        basename="u2",
    )
    with pytest.raises(ValueError, match="лимит"):
        recording_svc.start_recording(
            stream_url="https://a.com/3.m3u8",
            storage_mode=1,
            subpath=None,
            basename="u3",
        )


def test_stop_recording_false_when_not_recording(recording_svc: RecordingService):
    store = recording_svc._store
    sid = store.create_session(
        stream_url="https://x.m3u8",
        storage_mode=1,
        subpath=None,
        basename="z",
        current_part=1,
        max_continuations=3,
        browser_download_hint=False,
        status="stopped",
        pid=None,
        current_output_path="z_001.mp4",
    )
    assert recording_svc.stop_recording(sid) is False


def test_stop_recording_true_while_recording(recording_svc: RecordingService):
    sid, _, _ = recording_svc.start_recording(
        stream_url="https://x.m3u8",
        storage_mode=1,
        subpath=None,
        basename="live",
    )
    assert recording_svc.stop_recording(sid) is True


def test_repeat_from_history_missing_raises(recording_svc: RecordingService):
    with pytest.raises(ValueError, match="истории не найдена"):
        recording_svc.repeat_from_history(str(uuid.uuid4()))


def test_current_recording_file_bytes_stopped_with_file(recording_svc: RecordingService):
    root = recording_svc.recordings_root
    rel = "sz_001.mp4"
    (root / rel).write_bytes(b"abc" * 4000)
    store = recording_svc._store
    sid = store.create_session(
        stream_url="https://x.m3u8",
        storage_mode=1,
        subpath=None,
        basename="sz",
        current_part=1,
        max_continuations=3,
        browser_download_hint=False,
        status="stopped",
        pid=None,
        current_output_path=rel,
    )
    assert recording_svc.current_recording_file_bytes(sid) >= 12000
