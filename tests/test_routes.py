"""HTTP-маршруты Flask (test_client + изолированное окружение)."""

from __future__ import annotations

import subprocess
import time
import uuid
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


def _start_one_session(client):
    client.post(
        "/record/start",
        data={
            "url": "https://example.com/live/index.m3u8",
            "basename": "route_bn",
            "storage_mode": "1",
        },
        follow_redirects=True,
    )


def test_record_stop_flash_success(client):
    _start_one_session(client)
    sid = client.get("/record/status").get_json()["sessions"][0]["id"]
    r = client.post(f"/record/stop/{sid}", follow_redirects=True)
    assert r.status_code == 200
    assert "Остановка отправлена" in r.data.decode()


def test_record_stop_unknown_session(client):
    bad = str(uuid.uuid4())
    r = client.post(f"/record/stop/{bad}", follow_redirects=True)
    assert r.status_code == 200
    body = r.data.decode()
    assert "не найдена" in body or "уже не записывается" in body


def test_record_start_session_limit_flash(client):
    client.post(
        "/record/start",
        data={
            "url": "https://example.com/a.m3u8",
            "basename": "lim1",
            "storage_mode": "1",
        },
        follow_redirects=True,
    )
    client.post(
        "/record/start",
        data={
            "url": "https://example.com/b.m3u8",
            "basename": "lim2",
            "storage_mode": "1",
        },
        follow_redirects=True,
    )
    # Flash одноразовый: брать ответ именно после третьего POST (редирект на /), без лишнего GET.
    r = client.post(
        "/record/start",
        data={
            "url": "https://example.com/c.m3u8",
            "basename": "lim3",
            "storage_mode": "1",
        },
        follow_redirects=True,
    )
    assert "лимит" in r.data.decode().lower()


def test_files_download(client, tmp_media_root):
    root = Path(tmp_media_root["RECORDINGS_ROOT"])
    (root / "route_dl_001.mp4").write_bytes(b"fake-mp4-bytes")
    r = client.get("/files/download/route_dl_001.mp4")
    assert r.status_code == 200
    assert r.data == b"fake-mp4-bytes"


def test_files_download_404(client):
    assert client.get("/files/download/absent_001.mp4").status_code == 404


def test_files_info_ok(monkeypatch, client, tmp_media_root):
    root = Path(tmp_media_root["RECORDINGS_ROOT"])
    (root / "probe_001.mp4").write_bytes(b"x")

    def fake_run(*_a, **_kw):
        return subprocess.CompletedProcess(
            [], returncode=0, stdout="FORMAT_LINE_OK", stderr=""
        )

    monkeypatch.setattr("recorder.blueprints.main.subprocess.run", fake_run)
    r = client.get("/files/info/probe_001.mp4")
    assert r.status_code == 200
    assert b"FORMAT_LINE_OK" in r.data


def test_files_info_404(client):
    assert client.get("/files/info/missing_001.mp4").status_code == 404


def test_files_info_timeout(monkeypatch, client, tmp_media_root):
    root = Path(tmp_media_root["RECORDINGS_ROOT"])
    (root / "to_001.mp4").write_bytes(b"x")

    def boom(*_a, **_kw):
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=1)

    monkeypatch.setattr("recorder.blueprints.main.subprocess.run", boom)
    assert client.get("/files/info/to_001.mp4").status_code == 504


def test_files_check_ok(monkeypatch, client, tmp_media_root):
    root = Path(tmp_media_root["RECORDINGS_ROOT"])
    (root / "chk_001.mp4").write_bytes(b"x")

    def fake_run(*_a, **_kw):
        return subprocess.CompletedProcess([], returncode=0, stdout="", stderr="")

    monkeypatch.setattr("recorder.blueprints.main.subprocess.run", fake_run)
    r = client.post("/files/check/chk_001.mp4", follow_redirects=True)
    assert r.status_code == 200
    assert "Целостность: OK" in r.data.decode()


def test_files_check_error_flash(monkeypatch, client, tmp_media_root):
    root = Path(tmp_media_root["RECORDINGS_ROOT"])
    (root / "bad_001.mp4").write_bytes(b"x")

    def fake_run(*_a, **_kw):
        return subprocess.CompletedProcess(
            [], returncode=1, stdout="", stderr="broken stream"
        )

    monkeypatch.setattr("recorder.blueprints.main.subprocess.run", fake_run)
    r = client.post("/files/check/bad_001.mp4", follow_redirects=True)
    assert r.status_code == 200
    assert "Проблемы" in r.data.decode()


def test_files_delete_ok(client, tmp_media_root):
    root = Path(tmp_media_root["RECORDINGS_ROOT"])
    p = root / "del_route_001.mp4"
    p.write_bytes(b"z")
    r = client.post(
        "/files/delete",
        data={"rel_path": "del_route_001.mp4", "confirm": "yes"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert not p.is_file()


def test_files_delete_requires_confirm(client, tmp_media_root):
    root = Path(tmp_media_root["RECORDINGS_ROOT"])
    p = root / "keep_route_001.mp4"
    p.write_bytes(b"z")
    client.post(
        "/files/delete",
        data={"rel_path": "keep_route_001.mp4"},
        follow_redirects=True,
    )
    assert p.is_file()


def test_files_delete_not_found(client):
    r = client.post(
        "/files/delete",
        data={"rel_path": "nope_001.mp4", "confirm": "yes"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "не найден" in r.data.decode()


def test_recording_history_delete(client):
    _start_one_session(client)
    items = client.get("/record/history/api").get_json()["items"]
    assert len(items) >= 1
    hid = items[0]["id"]
    r = client.post(f"/record/history/delete/{hid}", follow_redirects=True)
    assert r.status_code == 200
    assert "удалена из истории" in r.data.decode()
    assert client.get("/record/history/api").get_json()["items"] == []


def test_recording_repeat_from_history(client):
    client.post(
        "/record/start",
        data={
            "url": "https://example.com/rep.m3u8",
            "basename": "repuniq",
            "storage_mode": "1",
        },
        follow_redirects=True,
    )
    hid = client.get("/record/history/api").get_json()["items"][0]["id"]
    r = client.post(f"/record/repeat/{hid}", follow_redirects=True)
    assert r.status_code == 200
    body = r.data.decode()
    assert "repuniq" in body or "истории" in body.lower()
    st = client.get("/record/status").get_json()["sessions"]
    assert (
        sum(
            1
            for s in st
            if s["basename"] == "repuniq" and s["status"] == "recording"
        )
        == 2
    )


def test_recording_repeat_unknown_history(client):
    bad = str(uuid.uuid4())
    r = client.post(f"/record/repeat/{bad}", follow_redirects=True)
    assert r.status_code == 200
    assert "не найдена" in r.data.decode()
