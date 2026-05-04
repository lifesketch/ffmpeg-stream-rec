"""Управление сессиями записи и процессами FFmpeg."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psutil

from . import ffmpeg_utils, paths_util, process_utils
from .store import SessionRow, SessionStore


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ffmpeg_stderr_tail_for_diagnostics(raw: bytes, *, max_chars: int = 6000) -> str:
    """
    Срез stderr для логов. Баннер «ffmpeg version … configuration:» занимает десятки KiB;
    при взятии «последних N символов» реальная ошибка (часто в начале короткого stderr)
    теряется — ищем типичные маркеры и берём хвост с последнего вхождения.
    """
    if not raw:
        return ""
    s = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    for needle in (
        "Conversion failed!",
        "Invalid data found",
        "Server returned ",
        "HTTP error",
        "Protocol not found",
        "Error opening",
        "Error while opening",
        "Assertion ",
        "Unknown format",
        "Option ",
        "[hls @",
        "Input #0,",
    ):
        i = s.rfind(needle)
        if i != -1:
            chunk = s[i:]
            if len(chunk) > max_chars:
                return chunk[: max_chars - 1] + "…"
            return chunk
    if len(s) <= max_chars:
        return s
    return "…" + s[-max_chars:]


class RecordingService:
    def __init__(self, config: dict, store: SessionStore, logger) -> None:
        self._cfg = config
        self._store = store
        self._log = logger
        self._lock = threading.Lock()
        self._shutdown_all_lock = threading.Lock()
        self._local_procs: dict[str, subprocess.Popen] = {}

    @property
    def recordings_root(self) -> Path:
        return Path(self._cfg["RECORDINGS_ROOT"])

    def _ffmpeg_stderr_log_path(self, session_id: str) -> Path:
        return Path(self._cfg["LOG_DIR"]) / f"ffmpeg-{session_id}.log"

    def _unlink_ffmpeg_stderr_log(self, session_id: str) -> None:
        try:
            self._ffmpeg_stderr_log_path(session_id).unlink(missing_ok=True)
        except OSError:
            pass

    def restore_after_restart(self) -> None:
        for row in self._store.list_all():
            if row.status != "recording":
                continue
            pid = row.pid
            if pid and process_utils.process_exists(pid):
                self._log.info(
                    "Восстановление сессии %s: процесс pid=%s жив", row.id, pid
                )
                threading.Thread(
                    target=self._watch_external_pid,
                    args=(row.id, pid),
                    daemon=True,
                    name=f"watch-{row.id}",
                ).start()
            else:
                self._log.warning(
                    "Сессия %s: процесс не найден после перезапуска — обработка выхода",
                    row.id,
                )
                self._handle_process_exit(row.id, exit_code=-1, stderr_tail="")

    def start_recording(
        self,
        *,
        stream_url: str,
        storage_mode: int,
        subpath: str | None,
        basename: str,
    ) -> tuple[str, str, int]:
        """Возвращает (session_id, basename, номер_первой_части на диске)."""
        stream_url = paths_util.validate_stream_url(stream_url)
        raw_bn = (basename or "").strip()
        if not raw_bn:
            raw_bn = str(self._cfg.get("DEFAULT_RECORDING_BASENAME", "steam1"))
        basename = paths_util.validate_basename(raw_bn)
        basename = paths_util.normalize_basename_legacy_collisions(basename)
        if storage_mode not in (1, 2, 3):
            raise ValueError("Недопустимый режим хранения")
        if storage_mode == 2:
            paths_util.sanitize_subpath(subpath)
        else:
            subpath = None

        max_sess = int(self._cfg["MAX_INDEPENDENT_SESSIONS"])
        if self._store.count_recording() >= max_sess:
            raise ValueError(
                f"Достигнут лимит активных записей ({max_sess} независимых сессий)"
            )

        part = paths_util.allocate_unique_starting_part(
            self.recordings_root,
            storage_mode,
            subpath,
            basename,
        )
        out_path = paths_util.output_mp4_path(
            self.recordings_root,
            storage_mode,
            subpath,
            basename,
            part,
        )
        browser_hint = storage_mode == 3

        args = ffmpeg_utils.build_record_args(
            self._cfg["FFMPEG_BIN"],
            stream_url,
            out_path,
        )

        sid = str(uuid.uuid4())
        log_path = self._ffmpeg_stderr_log_path(sid)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_f = open(log_path, "wb")
        try:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=log_f,
                close_fds=True,
            )
        except Exception:
            log_f.close()
            log_path.unlink(missing_ok=True)
            raise
        rel = paths_util.relative_to_recordings(self.recordings_root, out_path)

        self._store.create_session(
            session_id=sid,
            stream_url=stream_url,
            storage_mode=storage_mode,
            subpath=subpath,
            basename=basename,
            current_part=part,
            max_continuations=int(self._cfg["MAX_CONTINUATIONS"]),
            browser_download_hint=browser_hint,
            status="recording",
            pid=proc.pid,
            current_output_path=rel,
        )
        self._local_procs[sid] = proc

        threading.Thread(
            target=self._watch_popen,
            args=(sid, proc),
            daemon=True,
            name=f"watch-{sid}",
        ).start()
        self._log.info("Старт записи sid=%s pid=%s файл=%s", sid, proc.pid, rel)
        try:
            self._store.add_recording_history(
                stream_url=stream_url,
                basename=basename,
                storage_mode=storage_mode,
                subpath=subpath,
            )
        except Exception:
            self._log.exception("Не удалось сохранить историю записи")
        if part != 1:
            self._log.info(
                "Первая свободная часть для «%s»: %03d (файл %s_%03d.mp4)",
                basename,
                part,
                basename,
                part,
            )
        return sid, basename, part

    def ffmpeg_stderr_preview(self, session_id: str) -> str:
        """Хвост лога FFmpeg с диска (stderr пишется в LOG_DIR/ffmpeg-<sid>.log)."""
        p = self._ffmpeg_stderr_log_path(session_id)
        try:
            if not p.is_file() or p.stat().st_size == 0:
                return ""
            with open(p, "rb") as f:
                f.seek(0, 2)
                sz = f.tell()
                f.seek(max(0, sz - 6000))
                return f.read().decode("utf-8", errors="replace")
        except OSError:
            return ""

    def _watch_popen(self, session_id: str, proc: subprocess.Popen) -> None:
        """
        Ждать FFmpeg. stderr направляется в файл: так нет риска заполнить пайп (~64 KiB)
        и заблокировать FFmpeg до появления данных в MP4 (особенно на HLS/HTTPS).
        """
        rc = 0
        try:
            rc = proc.wait()
        finally:
            if proc.stderr is not None:
                try:
                    proc.stderr.close()
                except OSError:
                    pass
        self._local_procs.pop(session_id, None)
        raw = b""
        try:
            lp = self._ffmpeg_stderr_log_path(session_id)
            if lp.is_file():
                raw = lp.read_bytes()
        except OSError:
            pass
        stderr_tail = _ffmpeg_stderr_tail_for_diagnostics(raw)
        self._handle_process_exit(session_id, exit_code=rc, stderr_tail=stderr_tail)

    def _watch_external_pid(self, session_id: str, pid: int) -> None:
        rc = -1
        try:
            p = psutil.Process(pid)
            rc = int(p.wait(timeout=None))
        except psutil.NoSuchProcess:
            rc = -1
        except Exception:
            self._log.exception("Ошибка ожидания внешнего PID %s", pid)
            rc = -1
        self._handle_process_exit(session_id, exit_code=rc, stderr_tail="")

    def _maybe_register_finished_part(self, row: SessionRow) -> None:
        rel_output = row.current_output_path
        if not rel_output:
            return
        try:
            abs_path = paths_util.resolve_existing_mp4(self.recordings_root, rel_output)
            if abs_path.stat().st_size > 0:
                self._store.append_completed_part(row.id, rel_output)
        except (OSError, ValueError, FileNotFoundError):
            pass

    def _handle_process_exit(
        self,
        session_id: str,
        *,
        exit_code: int,
        stderr_tail: str,
    ) -> None:
        with self._lock:
            row = self._store.get(session_id)
            if not row:
                return

            self._maybe_register_finished_part(row)
            manual_stop = row.manual_stop

            if manual_stop:
                self._store.update(
                    session_id,
                    status="stopped",
                    pid=None,
                    manual_stop=False,
                    ended_at=_utc_iso(),
                )
                self._log.info("Сессия %s остановлена вручную", session_id)
                self._unlink_ffmpeg_stderr_log(session_id)
                return

            if exit_code == 0:
                self._store.update(
                    session_id,
                    status="completed",
                    pid=None,
                    ended_at=_utc_iso(),
                )
                self._log.info("Сессия %s завершилась штатно", session_id)
                self._unlink_ffmpeg_stderr_log(session_id)
                return

            self._log.warning(
                "Сессия %s аварийное завершение code=%s tail=%s",
                session_id,
                exit_code,
                (stderr_tail[:800] + "…") if len(stderr_tail) > 800 else stderr_tail,
            )

            if row.continuation_count >= row.max_continuations:
                self._store.update(
                    session_id,
                    status="failed",
                    pid=None,
                    ended_at=_utc_iso(),
                )
                self._log.error(
                    "Сессия %s: исчерпан лимит авто-продолжений", session_id
                )
                self._unlink_ffmpeg_stderr_log(session_id)
                return

            next_part = row.current_part + 1
            new_count = row.continuation_count + 1
            self._store.update(
                session_id,
                continuation_count=new_count,
                current_part=next_part,
                pid=None,
            )
            try:
                self._spawn_continuation(session_id)
            except Exception:
                self._log.exception("Не удалось продолжить запись %s", session_id)
                self._store.update(
                    session_id,
                    status="failed",
                    pid=None,
                    ended_at=_utc_iso(),
                )
                self._unlink_ffmpeg_stderr_log(session_id)

    def _spawn_continuation(self, session_id: str) -> None:
        row = self._store.get(session_id)
        if not row:
            return
        out_path = paths_util.output_mp4_path(
            self.recordings_root,
            row.storage_mode,
            row.subpath,
            row.basename,
            row.current_part,
        )
        args = ffmpeg_utils.build_record_args(
            self._cfg["FFMPEG_BIN"],
            row.stream_url,
            out_path,
        )
        log_path = self._ffmpeg_stderr_log_path(session_id)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_f = open(log_path, "ab")
        try:
            proc = subprocess.Popen(
                args,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=log_f,
                close_fds=True,
            )
        except Exception:
            log_f.close()
            raise
        rel = paths_util.relative_to_recordings(self.recordings_root, out_path)
        self._store.update(
            session_id,
            status="recording",
            pid=proc.pid,
            current_output_path=rel,
        )
        self._local_procs[session_id] = proc
        threading.Thread(
            target=self._watch_popen,
            args=(session_id, proc),
            daemon=True,
            name=f"watch-{session_id}",
        ).start()
        self._log.info(
            "Авто-продолжение sid=%s часть=%s pid=%s файл=%s",
            session_id,
            row.current_part,
            proc.pid,
            rel,
        )

    def graceful_shutdown_all_recordings(self, *, reason: str = "") -> None:
        """
        Остановить все активные записи так же, как по кнопке «Стоп».
        Вызывается при завершении процесса сервера (сигнал / atexit), чтобы FFmpeg
        успел закрыть контейнер MP4 и сессии не ушли в авто-продолжение после рестарта.
        """
        wait_sec = float(self._cfg.get("RECORDING_SHUTDOWN_WAIT_SEC", 90))
        with self._shutdown_all_lock:
            ids = [s.id for s in self.list_sessions() if s.status == "recording"]
            if not ids:
                return
            for sid in ids:
                try:
                    self.stop_recording(sid)
                except Exception:
                    self._log.exception(
                        "Не удалось запросить остановку сессии %s при shutdown", sid
                    )
            deadline = time.monotonic() + wait_sec
            while time.monotonic() < deadline:
                if not any(s.status == "recording" for s in self.list_sessions()):
                    break
                time.sleep(0.15)
            else:
                self._log.warning(
                    "Таймаут %.0f с: часть сессий всё ещё recording после остановки сервера",
                    wait_sec,
                )
            self._log.info(
                "Остановка записей при завершении сервера (%s), сессий: %d",
                reason or "—",
                len(ids),
            )

    def stop_recording(self, session_id: str) -> bool:
        row = self._store.get(session_id)
        if not row or row.status != "recording":
            return False
        self._store.update(session_id, manual_stop=True)
        pid = row.pid
        if pid:
            process_utils.graceful_terminate(pid)
        proc = self._local_procs.get(session_id)
        if proc and proc.poll() is None and proc.pid:
            process_utils.graceful_terminate(proc.pid)
        self._log.info("Запрошена остановка сессии %s", session_id)
        return True

    def list_sessions(self) -> list[SessionRow]:
        return self._store.list_all()

    def _live_bytes_via_proc_fd(self, pid: int, expected_name: str) -> int | None:
        """
        В Docker/NAS иногда путь из БД и реальный выход FFmpeg расходятся; по открытым fd
        процесса находим файл с ожидаемым именем под RECORDINGS_ROOT.
        Только Linux (/proc).
        """
        if sys.platform != "linux" or pid <= 0:
            return None
        root = self.recordings_root.resolve()
        fd_dir = Path(f"/proc/{pid}/fd")
        try:
            if not fd_dir.is_dir():
                return None
        except OSError:
            return None
        for item in fd_dir.iterdir():
            if not item.name.isdigit():
                continue
            try:
                target = os.readlink(item)
            except OSError:
                continue
            try:
                cand = Path(target).resolve()
                if cand.name != expected_name:
                    continue
                cand.relative_to(root)
            except (ValueError, OSError):
                continue
            try:
                st = cand.stat()
                if not stat.S_ISREG(st.st_mode):
                    continue
                return int(st.st_size)
            except OSError:
                continue
        return None

    def current_recording_file_bytes(self, session_id: str) -> int:
        """Размер текущего выходного .mp4 в байтах (0 если не идёт запись или файла ещё нет)."""
        row = self._store.get(session_id)
        if not row or row.status != "recording" or not row.current_output_path:
            return 0
        expected_name = f"{row.basename}_{row.current_part:03d}.mp4"
        try:
            p = paths_util.resolve_mp4_under_recordings_root(
                self.recordings_root, row.current_output_path
            )
            if p.is_file():
                return int(p.stat().st_size)
        except (OSError, ValueError, FileNotFoundError):
            pass

        if row.pid:
            via_proc = self._live_bytes_via_proc_fd(int(row.pid), expected_name)
            if via_proc is not None:
                return via_proc

        return 0

    def completed_parts(self, session_id: str) -> list[str]:
        row = self._store.get(session_id)
        if not row:
            return []
        return json.loads(row.completed_parts_json or "[]")

    def list_recording_history(self):
        return self._store.list_recording_history()

    def delete_recording_history(self, history_id: str) -> bool:
        return self._store.delete_recording_history(history_id)

    def repeat_from_history(self, history_id: str) -> tuple[str, str, int]:
        h = self._store.get_recording_history(history_id)
        if not h:
            raise ValueError("Запись истории не найдена")
        return self.start_recording(
            stream_url=h.stream_url,
            storage_mode=h.storage_mode,
            subpath=h.subpath,
            basename=h.basename,
        )
