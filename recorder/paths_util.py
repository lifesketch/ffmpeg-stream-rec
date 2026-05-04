"""Безопасные пути записи и валидация имён."""
from __future__ import annotations

import re
from pathlib import Path

_URL_PREFIXES = ("http://", "https://")
_BASENAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


def normalize_stream_url_input(url: str) -> str:
    """Убрать пробелы по краям и невидимые символы копипаста (BOM, zero-width, NBSP)."""
    u = (url or "").strip()
    for ch in ("\ufeff", "\u200b", "\u200c", "\u200d", "\xa0"):
        u = u.replace(ch, "")
    return u.strip()


def validate_stream_url(url: str) -> str:
    u = normalize_stream_url_input(url)
    if not u.startswith(_URL_PREFIXES):
        raise ValueError("URL должен начинаться с http:// или https://")
    return u


def validate_basename(name: str) -> str:
    n = (name or "").strip()
    if not _BASENAME_RE.fullmatch(n):
        raise ValueError(
            "Имя файла: только латиница, цифры, _ и -, длина 1–80 символов"
        )
    return n


def normalize_basename_legacy_collisions(validated_basename: str) -> str:
    """
    Убрать хвост из склеенных троек 001, 002, … (0XX), которые добавлял старый
    алгоритм коллизий без подчёркивания. Иначе «Повторить из истории» раздувает имя:
    recording → recording001 → recording001001 → …
    Имена вроде steam1 или steam123 не затрагиваются (123 не начинается с 0).
    """
    n = validated_basename.strip()
    if not n:
        return n
    m = re.match(r"^(.+?)((?:0\d{2})+)$", n)
    if not m:
        return n
    head = m.group(1)
    if not head or not _BASENAME_RE.fullmatch(head):
        return n
    return head


def sanitize_subpath(subpath: str | None) -> Path:
    """Относительный путь для режима 2b внутри RECORDINGS_ROOT."""
    if subpath is None or not str(subpath).strip():
        raise ValueError("Для режима 2b укажите подпапку внутри корня записи")
    raw = str(subpath).strip().replace("\\", "/")
    parts: list[str] = []
    for part in Path(raw).parts:
        if part in (".", ""):
            continue
        if part == "..":
            raise ValueError("Запрещён выход из корня (..)")
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", part):
            raise ValueError(f"Недопустимый сегмент пути: {part}")
        parts.append(part)
    if not parts:
        raise ValueError("Пустой относительный путь")
    return Path(*parts)


def recording_base_dir(recordings_root: Path, storage_mode: int, subpath: str | None) -> Path:
    root = recordings_root.resolve()
    if storage_mode == 2:
        rel = sanitize_subpath(subpath)
        target = (root / rel).resolve()
        target.relative_to(root)
        return target
    return root


def expected_output_mp4_path(
    recordings_root: Path,
    storage_mode: int,
    subpath: str | None,
    basename: str,
    part: int,
) -> Path:
    """Ожидаемый путь к части без создания каталогов (для проверки коллизий)."""
    base = recording_base_dir(recordings_root, storage_mode, subpath)
    name = f"{validate_basename(basename)}_{part:03d}.mp4"
    out = (base / name).resolve()
    root = recordings_root.resolve()
    out.relative_to(root)
    if out.suffix.lower() != ".mp4":
        raise ValueError("Разрешены только файлы .mp4")
    return out


def allocate_unique_starting_part(
    recordings_root: Path,
    storage_mode: int,
    subpath: str | None,
    basename: str,
    *,
    max_attempts: int = 500,
) -> int:
    """
    Первый номер части p ≥ 1, для которого файла {basename}_{p:03d}.mp4 ещё нет.
    Базовое имя не меняется — только суффикс _001, _002 в имени файла.
    """
    base = validate_basename(basename)
    for part in range(1, max_attempts + 1):
        target = expected_output_mp4_path(
            recordings_root, storage_mode, subpath, base, part
        )
        if not target.is_file():
            return part
    raise ValueError(
        "Не удалось найти свободный номер части в каталоге назначения "
        "(слишком много файлов)"
    )


def output_mp4_path(
    recordings_root: Path,
    storage_mode: int,
    subpath: str | None,
    basename: str,
    part: int,
) -> Path:
    base = recording_base_dir(recordings_root, storage_mode, subpath)
    base.mkdir(parents=True, exist_ok=True)
    name = f"{validate_basename(basename)}_{part:03d}.mp4"
    out = (base / name).resolve()
    root = recordings_root.resolve()
    out.relative_to(root)
    if out.suffix.lower() != ".mp4":
        raise ValueError("Разрешены только файлы .mp4")
    return out


def resolve_mp4_under_recordings_root(recordings_root: Path, rel_path: str) -> Path:
    """
    Безопасный путь к .mp4 внутри RECORDINGS_ROOT.
    rel_path — как в БД (относительный), либо абсолютный путь уже под тем же корнем
    (копии БД / ручные правки), чтобы не получить «двойной» корень после lstrip('/').
    """
    root = recordings_root.resolve()
    raw_in = (rel_path or "").strip().replace("\\", "/")
    if not raw_in:
        raise ValueError("Некорректный путь")
    p_in = Path(raw_in)
    if ".." in p_in.parts:
        raise ValueError("Некорректный путь")
    if p_in.is_absolute():
        candidate = p_in.resolve()
    else:
        candidate = (root / raw_in.lstrip("/")).resolve()
    candidate.relative_to(root)
    if candidate.suffix.lower() != ".mp4":
        raise ValueError("Ожидался .mp4")
    return candidate


def resolve_existing_mp4(recordings_root: Path, rel_path: str) -> Path:
    """Путь к уже существующему mp4 относительно RECORDINGS_ROOT."""
    candidate = resolve_mp4_under_recordings_root(recordings_root, rel_path)
    if not candidate.is_file():
        raise FileNotFoundError("Файл не найден")
    return candidate


def relative_to_recordings(recordings_root: Path, absolute: Path) -> str:
    return str(absolute.resolve().relative_to(recordings_root.resolve()))
