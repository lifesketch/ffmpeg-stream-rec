"""Маршруты UI и API записи."""
from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from .. import auth, ffmpeg_utils, paths_util

bp = Blueprint("main", __name__)

INDEX_PAGE_SIZE = 5


def format_iso_local(iso_str: str | None) -> str:
    """Вывод даты/времени в локальной зоне для ISO-строки UTC."""
    if not iso_str:
        return "—"
    try:
        s = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso_str


def _file_saved_at_local(path: Path) -> str:
    """Дата и время последней модификации файла на диске (локальная зона)."""
    try:
        ts = path.stat().st_mtime
    except OSError:
        return "—"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


@bp.before_request
def _optional_bearer_auth() -> None:
    token = (current_app.config.get("AUTH_TOKEN") or "").strip()
    if not token:
        return None
    if not auth.valid_bearer(request, token):
        abort(401)


def _svc():
    return current_app.extensions["recording_service"]


def _list_mp4_files(root: Path) -> list[Path]:
    root = root.resolve()
    out: list[Path] = []
    for p in root.rglob("*.mp4"):
        try:
            p.resolve().relative_to(root)
        except ValueError:
            continue
        if p.is_file():
            out.append(p)

    def _mtime_key(pp: Path) -> float:
        try:
            return pp.stat().st_mtime
        except OSError:
            return 0.0

    out.sort(key=_mtime_key, reverse=True)
    return out


def _safe_page_arg(name: str) -> int:
    try:
        return max(1, int(request.args.get(name, 1)))
    except (TypeError, ValueError):
        return 1


def _paginate(items: list, page: int, per_page: int) -> tuple[list, dict]:
    total = len(items)
    pages = max(1, (total + per_page - 1) // per_page) if total else 1
    page = max(1, min(page, pages))
    start_idx = (page - 1) * per_page
    chunk = items[start_idx : start_idx + per_page]
    range_start = start_idx + 1 if total else 0
    range_end = start_idx + len(chunk) if total else 0
    return chunk, {
        "page": page,
        "pages": pages,
        "total": total,
        "per_page": per_page,
        "has_prev": page > 1,
        "has_next": page < pages,
        "range_start": range_start,
        "range_end": range_end,
    }


@bp.route("/")
def index():
    svc = _svc()
    sessions = svc.list_sessions()
    sessions_rows = []
    active_recordings = 0
    for s in sessions:
        parts = svc.completed_parts(s.id)
        live_bytes = svc.current_recording_file_bytes(s.id)
        if s.status == "recording":
            active_recordings += 1
        sessions_rows.append(
            {"session": s, "parts": parts, "live_bytes": live_bytes}
        )
    mp4_paths = _list_mp4_files(svc.recordings_root)
    files = [
        {
            "rel": paths_util.relative_to_recordings(svc.recordings_root, p),
            "saved_at": _file_saved_at_local(p),
        }
        for p in mp4_paths
    ]
    sp = _safe_page_arg("sessions_page")
    fp = _safe_page_arg("files_page")
    sessions_rows, sessions_pager = _paginate(sessions_rows, sp, INDEX_PAGE_SIZE)
    files, files_pager = _paginate(files, fp, INDEX_PAGE_SIZE)
    return render_template(
        "index.html",
        sessions_rows=sessions_rows,
        sessions_pager=sessions_pager,
        active_recordings=active_recordings,
        files=files,
        files_pager=files_pager,
        max_sessions=current_app.config["MAX_INDEPENDENT_SESSIONS"],
        default_basename=current_app.config["DEFAULT_RECORDING_BASENAME"],
    )


@bp.route("/record/start", methods=["POST"])
def record_start():
    svc = _svc()
    try:
        url = request.form.get("url", "").strip()
        basename = request.form.get("basename", "").strip()
        mode_raw = request.form.get("storage_mode", "1")
        storage_mode = int(mode_raw)
        subpath = request.form.get("subpath") or None
        if subpath:
            subpath = subpath.strip() or None
        _, bn, start_part = svc.start_recording(
            stream_url=url,
            storage_mode=storage_mode,
            subpath=subpath,
            basename=basename,
        )
        if start_part != 1:
            flash(
                f"Запись запущена: {bn}_{start_part:03d}.mp4 "
                f"(в каталоге уже были «{bn}_*.mp4», взята следующая свободная часть).",
                "success",
            )
        else:
            flash(f"Запись запущена: {bn}_{start_part:03d}.mp4", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("main.index"))


@bp.route("/record/stop/<session_id>", methods=["POST"])
def record_stop(session_id: str):
    svc = _svc()
    if not svc.stop_recording(session_id):
        flash("Сессия не найдена или уже не записывается", "error")
    else:
        flash("Остановка отправлена", "success")
    return redirect(url_for("main.index"))


@bp.route("/record/status")
def record_status():
    svc = _svc()
    out = []
    for s in svc.list_sessions():
        parts = svc.completed_parts(s.id)
        live_bytes = svc.current_recording_file_bytes(s.id)
        ff_excerpt = (
            svc.ffmpeg_stderr_preview(s.id) if s.status == "recording" else ""
        )
        out.append(
            {
                "id": s.id,
                "status": s.status,
                "pid": s.pid,
                "part": s.current_part,
                "basename": s.basename,
                "storage_mode": s.storage_mode,
                "browser_download_hint": s.browser_download_hint,
                "completed_parts": parts,
                "current_output_path": s.current_output_path,
                "current_file_bytes": live_bytes,
                "current_file_mb": round(live_bytes / (1024 * 1024), 2),
                "ffmpeg_stderr_excerpt": ff_excerpt,
                "created_at": s.created_at,
                "ended_at": s.ended_at,
                "started_at_local": format_iso_local(s.created_at),
                "ended_at_local": format_iso_local(s.ended_at),
            }
        )
    return jsonify({"sessions": out})


@bp.route("/record/history/api")
def recording_history_api():
    svc = _svc()
    items = []
    for h in svc.list_recording_history():
        items.append(
            {
                "id": h.id,
                "stream_url": h.stream_url,
                "basename": h.basename,
                "storage_mode": h.storage_mode,
                "subpath": h.subpath,
                "added_at": h.added_at,
                "added_at_local": format_iso_local(h.added_at),
            }
        )
    return jsonify({"items": items})


@bp.route("/record/history/delete/<history_id>", methods=["POST"])
def recording_history_delete(history_id: str):
    svc = _svc()
    if svc.delete_recording_history(history_id):
        flash("Запись удалена из истории", "success")
    else:
        flash("Элемент истории не найден", "error")
    return redirect(url_for("main.index"))


@bp.route("/record/repeat/<history_id>", methods=["POST"])
def recording_repeat(history_id: str):
    svc = _svc()
    try:
        _, bn, start_part = svc.repeat_from_history(history_id)
        if start_part != 1:
            flash(
                f"Запись по истории: {bn}_{start_part:03d}.mp4 "
                f"(первая свободная часть для этого имени).",
                "success",
            )
        else:
            flash(f"Запись по истории: {bn}_{start_part:03d}.mp4", "success")
    except Exception as e:
        flash(str(e), "error")
    return redirect(url_for("main.index"))


@bp.route("/files/info/<path:rel_path>")
def files_info(rel_path: str):
    svc = _svc()
    try:
        target = paths_util.resolve_existing_mp4(svc.recordings_root, rel_path)
    except (ValueError, FileNotFoundError):
        abort(404)
    args = ffmpeg_utils.build_ffprobe_format_args(
        current_app.config["FFPROBE_BIN"], target
    )
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        abort(504)
    body = proc.stdout
    if proc.stderr:
        body += "\n--- stderr ---\n" + proc.stderr
    return body, 200, {"Content-Type": "text/plain; charset=utf-8"}


@bp.route("/files/check/<path:rel_path>", methods=["POST"])
def files_check(rel_path: str):
    svc = _svc()
    try:
        target = paths_util.resolve_existing_mp4(svc.recordings_root, rel_path)
    except (ValueError, FileNotFoundError):
        abort(404)
    args = ffmpeg_utils.build_integrity_check_args(
        current_app.config["FFMPEG_BIN"], target
    )
    proc = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    ok = proc.returncode == 0
    flash(
        "Целостность: OK"
        if ok
        else f"Проблемы (код {proc.returncode}): {proc.stderr[:2000]}",
        "success" if ok else "error",
    )
    return redirect(url_for("main.index"))


@bp.route("/files/download/<path:rel_path>")
def files_download(rel_path: str):
    svc = _svc()
    try:
        target = paths_util.resolve_existing_mp4(svc.recordings_root, rel_path)
    except (ValueError, FileNotFoundError):
        abort(404)
    return send_file(
        target,
        as_attachment=True,
        download_name=target.name,
        max_age=0,
    )


@bp.route("/files/delete", methods=["POST"])
def files_delete():
    svc = _svc()
    rel_path = (request.form.get("rel_path") or "").strip()
    confirm = request.form.get("confirm") == "yes"
    if not confirm:
        flash("Удаление отменено: нужно подтверждение", "error")
        return redirect(url_for("main.index"))
    try:
        target = paths_util.resolve_existing_mp4(svc.recordings_root, rel_path)
    except (ValueError, FileNotFoundError):
        flash("Файл не найден", "error")
        return redirect(url_for("main.index"))
    try:
        target.unlink()
        flash(f"Удалено: {rel_path}", "success")
    except OSError as e:
        flash(f"Не удалось удалить: {e}", "error")
    return redirect(url_for("main.index"))
