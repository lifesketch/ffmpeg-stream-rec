"""Тесты Bearer-авторизации."""

from __future__ import annotations

from unittest.mock import MagicMock

from recorder.auth import valid_bearer


def test_valid_bearer_ok():
    req = MagicMock()
    req.headers = {"Authorization": "Bearer secret-token"}
    assert valid_bearer(req, "secret-token") is True


def test_valid_bearer_wrong_token():
    req = MagicMock()
    req.headers = {"Authorization": "Bearer other"}
    assert valid_bearer(req, "secret-token") is False


def test_valid_bearer_missing_header():
    req = MagicMock()
    req.headers = {}
    assert valid_bearer(req, "x") is False


def test_valid_bearer_not_bearer_scheme():
    req = MagicMock()
    req.headers = {"Authorization": "Basic xxx"}
    assert valid_bearer(req, "x") is False
