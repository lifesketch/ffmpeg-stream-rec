"""Построение аргументов FFmpeg / ffprobe (без shell)."""
from __future__ import annotations

from pathlib import Path


def build_record_args(
    ffmpeg_bin: str,
    stream_url: str,
    output_path: Path,
) -> list[str]:
    return [
        ffmpeg_bin,
        "-nostdin",
        # Не добавляем -reconnect*: на части HLS (в т.ч. .ts по HTTPS) FFmpeg уходит в цикл
        # «Will reconnect… error=End of file» и на диске 0 B, хотя без этих флагов поток идёт.
        "-i",
        stream_url,
        "-c",
        "copy",
        "-bsf:a",
        "aac_adtstoasc",
        "-y",
        str(output_path),
    ]


def build_integrity_check_args(ffmpeg_bin: str, file_path: Path) -> list[str]:
    return [
        ffmpeg_bin,
        "-v",
        "error",
        "-i",
        str(file_path),
        "-f",
        "null",
        "-",
    ]


def build_ffprobe_format_args(ffprobe_bin: str, file_path: Path) -> list[str]:
    return [
        ffprobe_bin,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
