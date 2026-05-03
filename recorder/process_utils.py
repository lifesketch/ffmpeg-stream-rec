"""Мягкая остановка дочернего процесса (POSIX)."""
from __future__ import annotations

import errno
import os
import signal
import time


def process_exists(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError as e:
        if e.errno == errno.ESRCH:
            return False
        raise
    return True


def graceful_terminate(pid: int, *, sigint_wait: float = 5.0, sigterm_wait: float = 5.0) -> None:
    """SIGINT → пауза → SIGTERM → пауза → SIGKILL."""
    if not process_exists(pid):
        return
    try:
        os.kill(pid, signal.SIGINT)
    except OSError:
        return
    deadline = time.monotonic() + sigint_wait
    while time.monotonic() < deadline:
        if not process_exists(pid):
            return
        time.sleep(0.2)
    if not process_exists(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    deadline = time.monotonic() + sigterm_wait
    while time.monotonic() < deadline:
        if not process_exists(pid):
            return
        time.sleep(0.2)
    if not process_exists(pid):
        return
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
