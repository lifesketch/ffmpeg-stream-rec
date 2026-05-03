import os


def _env_bool(name: str, default: bool) -> bool:
    raw = (os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw not in ("0", "false", "no", "off")


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-change-me")
    DEFAULT_RECORDING_BASENAME = os.environ.get(
        "DEFAULT_RECORDING_BASENAME", "steam1"
    ).strip() or "steam1"
    MAX_INDEPENDENT_SESSIONS = int(os.environ.get("MAX_INDEPENDENT_SESSIONS", "2"))
    MAX_CONTINUATIONS = int(os.environ.get("MAX_CONTINUATIONS", "5"))
    FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "ffmpeg")
    FFPROBE_BIN = os.environ.get("FFPROBE_BIN", "ffprobe")
    AUTH_TOKEN = os.environ.get("RECORDING_AUTH_TOKEN", "").strip()
    # При SIGTERM/SIGINT и при выходе процесса — мягкая остановка FFmpeg (как «Стоп» в UI).
    RECORDING_SHUTDOWN_HOOKS = _env_bool("RECORDING_SHUTDOWN_HOOKS", True)
    try:
        RECORDING_SHUTDOWN_WAIT_SEC = float(
            os.environ.get("RECORDING_SHUTDOWN_WAIT_SEC", "90")
        )
    except ValueError:
        RECORDING_SHUTDOWN_WAIT_SEC = 90.0
