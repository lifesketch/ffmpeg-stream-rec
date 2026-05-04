"""HTTP-маршруты Flask (test_client + изолированное окружение)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from recorder.store import SessionStore


def test_index_ok(client):
    r = client.get("/")
    assert r.status_code == 200


def test_index_files_sorted_newest_first_and_show_saved_at(client, tmp_media_root):
    root = Path(tmp_media_root["RECORDINGS_ROOT"])
    older = root / "pytest_file_order_old.mp4"
    newer = root / "pytest_file_order_new.mp4"
    older.write_bytes(b"x")
    time.sleep(0.06)
    newer.write_bytes(b"xy")
    r = client.get("/")
    assert r.status_code == 200
    text = r.data.decode()
    assert "Дата и время в каталоге" in text
    assert text.index("pytest_file_order_new.mp4") < text.index("pytest_file_order_old.mp4")


def test_record_start_redirect_and_session(app, client):
    r = client.post(
        "/record/start",
        data={
            "url": "https://example.com/live/index.m3u8",
            "basename": "pytest_bn",
            "storage_mode": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get("Location", "").endswith("/")

    svc = app.extensions["recording_service"]
    rows = svc.list_sessions()
    assert len(rows) >= 1
    latest = rows[0]
    assert latest.basename == "pytest_bn"
    assert latest.status == "recording"


def test_record_start_rejects_bad_url(client):
    r = client.post(
        "/record/start",
        data={
            "url": "not-a-url",
            "basename": "x",
            "storage_mode": "1",
        },
        follow_redirects=False,
    )
    assert r.status_code == 302
    fl = client.get("/")
    assert b"http://" in fl.data or b"URL" in fl.data


def test_record_status_json(client):
    r = client.get("/record/status")
    assert r.status_code == 200
    data = r.get_json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


def test_record_status_includes_file_size_when_stopped(app, client, tmp_media_root):
    """После остановки в JSON остаётся размер последнего mp4 (колонка «Размер на диске»)."""
    from recorder.store import SessionStore

    root = Path(tmp_media_root["RECORDINGS_ROOT"])
    rel = "done_001.mp4"
    (root / rel).write_bytes(b"x" * 15000)
    st = SessionStore(Path(tmp_media_root["STATE_DB_PATH"]))
    st.init_db()
    st.create_session(
        stream_url="https://example.com/x.m3u8",
        storage_mode=1,
        subpath=None,
        basename="done",
        current_part=1,
        max_continuations=3,
        browser_download_hint=False,
        status="stopped",
        pid=None,
        current_output_path=rel,
    )
    r = client.get("/record/status")
    assert r.status_code == 200
    sess = r.get_json()["sessions"][0]
    assert sess["status"] == "stopped"
    assert int(sess["current_file_bytes"]) >= 15000


def test_recording_history_api_empty(client):
    r = client.get("/record/history/api")
    assert r.status_code == 200
    assert r.get_json() == {"items": []}


def test_pagination_sessions_page(app, client, tmp_media_root):
    db_path = Path(tmp_media_root["STATE_DB_PATH"])
    store = SessionStore(db_path)
    store.init_db()
    for i in range(6):
        store.create_session(
            stream_url="https://example.com/a.m3u8",
            storage_mode=1,
            subpath=None,
            basename=f"s{i}",
            current_part=1,
            max_continuations=3,
            browser_download_hint=False,
            status="stopped",
            pid=None,
            current_output_path=f"s{i}_001.mp4",
        )

    r = client.get("/")
    assert r.status_code == 200
    assert r.data.count(b"data-session-id") == 5

    r2 = client.get("/?sessions_page=2&files_page=1")
    assert r2.status_code == 200
    assert r2.data.count(b"data-session-id") == 1


def test_bearer_auth_required(app, client):
    app.config["AUTH_TOKEN"] = "only-test-token"

    assert client.get("/").status_code == 401
    r = client.get("/", headers={"Authorization": "Bearer only-test-token"})
    assert r.status_code == 200
