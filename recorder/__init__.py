"""Flask-приложение записи HLS в MP4."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from .config import Config, _env_bool
from .service import RecordingService
from .shutdown_hooks import install_recording_shutdown_hooks
from .store import SessionStore


def _resolve_paths() -> dict[str, Path]:
    root = Path(os.environ.get("RECORDINGS_ROOT", "recordings"))
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    db = Path(os.environ.get("STATE_DB_PATH", "data/state.sqlite3"))
    if not db.is_absolute():
        db = (Path.cwd() / db).resolve()
    logdir = Path(os.environ.get("LOG_DIR", "logs"))
    if not logdir.is_absolute():
        logdir = (Path.cwd() / logdir).resolve()
    return {"RECORDINGS_ROOT": root, "STATE_DB_PATH": db, "LOG_DIR": logdir}


def create_app() -> Flask:
    load_dotenv()
    # Jupyter: перехват SIGINT в shutdown_hooks вызывает sys.exit и рвёт kernel при Interrupt.
    # Явно RECORDING_SHUTDOWN_HOOKS=1/true в .env — оставляем как есть (на свой риск).
    try:
        from IPython import get_ipython

        if get_ipython() is not None:
            raw = (os.environ.get("RECORDING_SHUTDOWN_HOOKS", "") or "").strip().lower()
            if raw not in ("1", "true", "yes", "on"):
                os.environ["RECORDING_SHUTDOWN_HOOKS"] = "0"
    except Exception:
        pass

    paths = _resolve_paths()

    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        instance_relative_config=False,
    )
    app.config.from_object(Config)
    app.config["RECORDINGS_ROOT"] = paths["RECORDINGS_ROOT"]
    app.config["STATE_DB_PATH"] = paths["STATE_DB_PATH"]
    app.config["LOG_DIR"] = paths["LOG_DIR"]
    # После load_dotenv / правок окружения (в т.ч. Jupyter) перечитать флаг.
    app.config["RECORDING_SHUTDOWN_HOOKS"] = _env_bool(
        "RECORDING_SHUTDOWN_HOOKS", True
    )

    paths["RECORDINGS_ROOT"].mkdir(parents=True, exist_ok=True)
    paths["STATE_DB_PATH"].parent.mkdir(parents=True, exist_ok=True)
    paths["LOG_DIR"].mkdir(parents=True, exist_ok=True)

    log_path = paths["LOG_DIR"] / "app.log"
    fh = RotatingFileHandler(log_path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    app.logger.addHandler(fh)
    app.logger.setLevel(logging.INFO)

    store = SessionStore(paths["STATE_DB_PATH"])
    store.init_db()
    service = RecordingService(app.config, store, app.logger)
    service.restore_after_restart()
    install_recording_shutdown_hooks(
        service,
        app.logger,
        enabled=bool(app.config.get("RECORDING_SHUTDOWN_HOOKS", True)),
    )
    app.extensions["recording_service"] = service

    from .blueprints.main import bp, format_iso_local

    app.register_blueprint(bp)
    app.template_filter("fmt_dt")(format_iso_local)

    app.logger.info(
        "Приложение создано: RECORDINGS_ROOT=%s STATE_DB=%s LOG_DIR=%s",
        paths["RECORDINGS_ROOT"],
        paths["STATE_DB_PATH"],
        paths["LOG_DIR"],
    )
    return app
