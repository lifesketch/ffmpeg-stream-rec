"""Тесты SQLite SessionStore."""

from __future__ import annotations

import json

import pytest

from recorder.store import SessionStore


@pytest.fixture
def store(tmp_path) -> SessionStore:
    db = tmp_path / "t.sqlite3"
    s = SessionStore(db)
    s.init_db()
    return s


def _mk_session_kwargs(**overrides):
    base = dict(
        stream_url="https://example.com/x.m3u8",
        storage_mode=1,
        subpath=None,
        basename="steam1",
        current_part=1,
        max_continuations=3,
        browser_download_hint=False,
        status="stopped",
        pid=None,
        current_output_path="steam1_001.mp4",
    )
    base.update(overrides)
    return base


def test_create_and_get(store):
    sid = store.create_session(**_mk_session_kwargs())
    row = store.get(sid)
    assert row is not None
    assert row.basename == "steam1"
    assert row.status == "stopped"


def test_create_session_explicit_id(store):
    fixed = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    sid = store.create_session(session_id=fixed, **_mk_session_kwargs())
    assert sid == fixed
    assert store.get(fixed) is not None


def test_count_recording(store):
    assert store.count_recording() == 0
    store.create_session(**_mk_session_kwargs(status="recording", pid=12345))
    assert store.count_recording() == 1


def test_update_manual_stop(store):
    sid = store.create_session(**_mk_session_kwargs(status="recording", pid=1))
    store.update(sid, manual_stop=True)
    assert store.get(sid).manual_stop is True


def test_append_completed_part(store):
    sid = store.create_session(**_mk_session_kwargs())
    store.append_completed_part(sid, "a_001.mp4")
    store.append_completed_part(sid, "a_001.mp4")
    row = store.get(sid)
    parts = json.loads(row.completed_parts_json)
    assert parts == ["a_001.mp4"]


def test_history_roundtrip(store):
    hid = store.add_recording_history(
        stream_url="https://x/y.m3u8",
        basename="b",
        storage_mode=2,
        subpath="nas",
    )
    rows = store.list_recording_history()
    assert len(rows) == 1
    assert rows[0].id == hid
    got = store.get_recording_history(hid)
    assert got is not None
    assert got.basename == "b"
    assert store.delete_recording_history(hid) is True
    assert store.get_recording_history(hid) is None
