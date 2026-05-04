"""
Отдельный процесс с Werkzeug (для Jupyter: надёжнее, чем daemon-thread в ядре).

Запуск из корня репозитория:
  .venv/bin/python -m recorder.dev_server_main

Переменные окружения (как у ноутбука): RECORDINGS_ROOT, STATE_DB_PATH, LOG_DIR,
RECORDING_FFMPEG_STDERR_PIPE, FLASK_RUN_HOST, FLASK_RUN_PORT.
После bind пишет notebooks/.dev_server_state.json и строку в stdout:
  JUPYTER_DEV_SERVER_READY http://127.0.0.1:PORT/
"""

from __future__ import annotations

import errno
import json
import os
import signal
import socket
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _state_path() -> Path:
    return _repo_root() / "notebooks" / ".dev_server_state.json"


def _remove_state() -> None:
    try:
        _state_path().unlink(missing_ok=True)
    except OSError:
        pass


def _write_state(payload: dict) -> None:
    p = _state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _listen_tcp(host: str, port: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen()
    return s


def main() -> None:
    root = _repo_root()
    os.chdir(root)
    rs = str(root)
    if rs not in sys.path:
        sys.path.insert(0, rs)

    host = os.environ.get("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_RUN_PORT", "5000"))

    os.environ.setdefault("RECORDINGS_ROOT", str((root / "recordings").resolve()))
    os.environ.setdefault(
        "STATE_DB_PATH", str((root / "data" / "state.sqlite3").resolve())
    )
    os.environ.setdefault("LOG_DIR", str((root / "logs").resolve()))
    os.environ.setdefault("RECORDING_FFMPEG_STDERR_PIPE", "0")
    os.environ.setdefault("RECORDING_SHUTDOWN_HOOKS", "0")

    # Снять зависший state от прошлого запуска
    sp = _state_path()
    if sp.is_file():
        try:
            old = json.loads(sp.read_text(encoding="utf-8"))
            opid = int(old.get("pid") or 0)
            if opid > 0:
                try:
                    os.kill(opid, 0)
                except OSError:
                    _remove_state()
        except (OSError, ValueError, json.JSONDecodeError):
            _remove_state()

    listen_port = port
    try:
        lsock = _listen_tcp(host, listen_port)
    except OSError as e:
        if e.errno != errno.EADDRINUSE:
            print(f"bind {host}:{listen_port}: {e}", file=sys.stderr)
            sys.exit(1)
        try:
            lsock = _listen_tcp(host, 0)
        except OSError as e2:
            print(f"bind {host}:0: {e2}", file=sys.stderr)
            sys.exit(1)
        listen_port = int(lsock.getsockname()[1])

    fd = lsock.detach()

    from werkzeug.serving import make_server

    from recorder import create_app

    app = create_app()
    srv = make_server(host, listen_port, app, threaded=True, fd=fd)

    client_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    url = f"http://{client_host}:{listen_port}/"

    _write_state(
        {
            "pid": os.getpid(),
            "url": url.rstrip("/"),
            "port": listen_port,
            "host": host,
        }
    )
    def _on_term(_signum, _frame):
        try:
            srv.shutdown()
        except Exception:
            pass

    signal.signal(signal.SIGTERM, _on_term)
    signal.signal(signal.SIGINT, _on_term)

    print("JUPYTER_DEV_SERVER_READY " + url, flush=True)
    try:
        srv.serve_forever()
    finally:
        _remove_state()


if __name__ == "__main__":
    main()
