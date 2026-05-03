"""Общие фикстуры: изолированные каталоги и безопасные моки процессов."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_media_root(tmp_path):
    """Корень записи + SQLite + логи внутри tmp_path."""
    root = tmp_path / "recordings"
    root.mkdir(parents=True)
    return {
        "RECORDINGS_ROOT": str(root),
        "STATE_DB_PATH": str(tmp_path / "state.sqlite3"),
        "LOG_DIR": str(tmp_path / "logs"),
    }


@pytest.fixture
def app(tmp_media_root, monkeypatch):
    """Flask-приложение без shutdown-hooks и без реального FFmpeg."""
    for key, val in tmp_media_root.items():
        monkeypatch.setenv(key, val)
    monkeypatch.setenv("RECORDING_SHUTDOWN_HOOKS", "0")
    monkeypatch.setenv("SECRET_KEY", "pytest-secret-key")
    monkeypatch.setenv("RECORDING_AUTH_TOKEN", "")

    def fake_popen(*_args, **_kwargs):
        proc = MagicMock()
        proc.pid = 999001
        proc.poll.return_value = None
        proc.stderr = None
        proc.wait.return_value = 0
        return proc

    monkeypatch.setattr("recorder.service.subprocess.Popen", fake_popen)
    monkeypatch.setattr(
        "recorder.service.RecordingService._watch_popen",
        lambda self, session_id, proc: None,
    )
    monkeypatch.setattr(
        "recorder.service.process_utils.graceful_terminate",
        lambda *_args, **_kwargs: None,
    )

    from recorder import create_app

    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()
