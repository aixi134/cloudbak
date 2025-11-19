from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable

logger = logging.getLogger(__name__)
FFMPEG_ENV = "FFMPEG_PATH"
_FFMPEG_STATUS: bool | None = None


def ffmpeg_path() -> str:
    return os.environ.get(FFMPEG_ENV, "ffmpeg")


def ffmpeg_available() -> bool:
    global _FFMPEG_STATUS
    if _FFMPEG_STATUS is not None:
        return _FFMPEG_STATUS
    try:
        subprocess.run([ffmpeg_path(), "-version"], capture_output=True, check=True)
        _FFMPEG_STATUS = True
        logger.info("FFmpeg detected: %s", ffmpeg_path())
    except Exception as exc:
        _FFMPEG_STATUS = False
        logger.warning("FFmpeg unavailable: %s", exc)
    return _FFMPEG_STATUS


def run_ffmpeg(args: list[str], stdin: bytes | None = None) -> bytes:
    logger.debug("Running ffmpeg %s", args)
    proc = subprocess.run(
        [ffmpeg_path(), *args],
        input=stdin,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg exited with {proc.returncode}: {proc.stderr.decode('utf-8', errors='ignore').strip()}"
        )
    if not proc.stdout:
        raise RuntimeError("ffmpeg produced empty output")
    return proc.stdout


def write_temp_frames(frames: Iterable[bytes]) -> str:
    fd, path = tempfile.mkstemp(prefix="wxgf_", suffix=".bin")
    with os.fdopen(fd, "wb") as tmp:
        for frame in frames:
            tmp.write(frame)
    return path


def cleanup_temp_files(paths: Iterable[str]):
    for path in paths:
        try:
            Path(path).unlink(missing_ok=True)
        except Exception:
            pass
