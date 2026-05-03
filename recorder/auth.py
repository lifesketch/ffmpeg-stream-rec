"""Опциональная авторизация по Bearer-токену."""
from __future__ import annotations

from functools import wraps

from flask import Request, abort, request


def require_auth_if_configured(auth_token: str):
    """Если RECORDING_AUTH_TOKEN задан — проверить заголовок Authorization."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not auth_token:
                return view_func(*args, **kwargs)
            if not valid_bearer(request, auth_token):
                abort(401)
            return view_func(*args, **kwargs)

        return wrapped

    return decorator


def valid_bearer(req: Request, expected: str) -> bool:
    h = req.headers.get("Authorization", "")
    prefix = "Bearer "
    if not h.startswith(prefix):
        return False
    return h[len(prefix) :].strip() == expected
