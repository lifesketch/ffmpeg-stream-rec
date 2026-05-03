"""Мягкая остановка записей при завершении процесса (SIGTERM/SIGINT, atexit)."""

from __future__ import annotations

import atexit
import signal
import sys


def install_recording_shutdown_hooks(service, logger, *, enabled: bool) -> None:
    if not enabled:
        return

    def shutdown(reason: str) -> None:
        try:
            service.graceful_shutdown_all_recordings(reason=reason)
        except Exception:
            logger.exception("Ошибка при остановке записей (%s)", reason)

    def on_signal(signum, frame):
        try:
            sig_name = signal.Signals(signum).name
        except ValueError:
            sig_name = str(signum)
        shutdown(f"signal {sig_name}")
        sys.exit(128 + signum)

    for sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if sig is None:
            continue
        try:
            signal.signal(sig, on_signal)
        except ValueError:
            logger.warning(
                "Не установлен обработчик %s (не главный поток процесса). "
                "Записи при Ctrl+C/SIGTERM могут не завершиться корректно — "
                "останавливайте сессии из UI или запускайте сервер из главного потока.",
                sig,
            )

    atexit.register(lambda: shutdown("выход процесса"))
