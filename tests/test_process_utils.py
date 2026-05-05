"""Тесты process_utils (без реальных сигналов дочерним процессам)."""

from __future__ import annotations

import os

from recorder import process_utils


def test_process_exists_none_and_non_positive():
    assert process_utils.process_exists(None) is False
    assert process_utils.process_exists(0) is False
    assert process_utils.process_exists(-1) is False


def test_process_exists_current_process():
    assert process_utils.process_exists(os.getpid()) is True


def test_graceful_terminate_noop_for_dead_pid():
    # Несуществующий PID не должен кидать исключение.
    process_utils.graceful_terminate(999_999_999)
