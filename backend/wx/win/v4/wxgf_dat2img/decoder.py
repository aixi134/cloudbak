from __future__ import annotations

import contextlib
import logging
import os
from typing import Tuple

from .ffmpeg_bridge import (
    cleanup_temp_files,
    ffmpeg_available,
    run_ffmpeg,
    write_temp_frames,
)
from .formats import WXGF
from .hevc import collect_parameter_sets, ensure_parameter_sets, fix_slice_headers
from .partitions import PartitionSet, find_partitions

logger = logging.getLogger(__name__)
DEBUG = bool(int(os.environ.get("WXGF_DEBUG", "0")))


def _debug(msg: str, *args):
    if DEBUG:
        print("[wxgf] " + msg.format(*args))


def _describe_partitions(partitions: PartitionSet):
    if not DEBUG:
        return
    _debug(
        "partitions: count={} max_index={} max_ratio={:.3f}",
        len(partitions.partitions),
        partitions.max_index,
        partitions.max_ratio,
    )
    for idx, part in enumerate(partitions.partitions):
        _debug(
            "  #{:02d} offset={} size={} ratio={:.3f}",
            idx,
            part.offset,
            part.size,
            part.ratio,
        )


def _convert_static(payload: bytes, params) -> Tuple[bytes, str]:
    _debug("static payload size={} bytes", len(payload))
    ensured = ensure_parameter_sets(payload, params)
    fixed = fix_slice_headers(ensured)
    if not ffmpeg_available():
        return ensured, "bin"
    inputs = [fixed, ensured] if fixed != ensured else [fixed]
    for attempt, data in enumerate(inputs, 1):
        try:
            jpg = run_ffmpeg(
                ["-f", "hevc", "-i", "pipe:0", "-vframes", "1", "-c:v", "mjpeg", "-q:v", "4", "-f", "image2", "pipe:1"],
                stdin=data,
            )
            return jpg, "jpg"
        except Exception as exc:
            logger.warning("Static FFmpeg attempt %d failed: %s", attempt, exc)
    return ensured, "bin"


def _convert_anime(anime_frames, mask_frames, params):
    _debug(
        "anime payload: frames={} mask_frames={} frame_size={} bytes",
        len(anime_frames),
        len(mask_frames),
        sum(len(f) for f in anime_frames) // max(len(anime_frames), 1),
    )
    ensured_anime = [ensure_parameter_sets(frame, params) for frame in anime_frames]
    ensured_mask = [ensure_parameter_sets(frame, params) for frame in mask_frames]
    fixed_anime = [fix_slice_headers(frame) for frame in ensured_anime]
    fixed_mask = [fix_slice_headers(frame) for frame in ensured_mask]
    candidates = [
        (fixed_anime, fixed_mask),
        (ensured_anime, ensured_mask),
    ]
    if not ffmpeg_available():
        return b"".join(ensured_anime), "bin"
    for attempt, (anime_list, mask_list) in enumerate(candidates, 1):
        anime_path = write_temp_frames(anime_list)
        mask_path = write_temp_frames(mask_list)
        try:
            gif = run_ffmpeg([
                "-f", "hevc", "-i", anime_path,
                "-f", "hevc", "-i", mask_path,
                "-filter_complex", "[0:v][1:v]alphamerge,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
                "-f", "gif",
                "-",
            ])
            cleanup_temp_files([anime_path, mask_path])
            return gif, "gif"
        except Exception as exc:
            logger.warning("Anime FFmpeg attempt %d failed: %s", attempt, exc)
        finally:
            cleanup_temp_files([anime_path, mask_path])
    return b"".join(ensured_anime), "bin"


def decode_wxgf(data: bytes) -> Tuple[bytes, str]:
    if len(data) < 15 or not data.startswith(WXGF.header):
        raise ValueError("invalid wxgf file")
    partitions = find_partitions(data)
    _describe_partitions(partitions)
    params = collect_parameter_sets([data[p.offset : p.offset + p.size] for p in partitions.partitions])
    if partitions.like_anime():
        anime_frames = []
        mask_frames = []
        for idx, part in enumerate(partitions.partitions):
            chunk = data[part.offset : part.offset + part.size]
            if idx % 2 == 0:
                mask_frames.append(chunk)
            else:
                anime_frames.append(chunk)
        return _convert_anime(anime_frames, mask_frames, params)
    target = partitions.partitions[partitions.max_index]
    payload = data[target.offset : target.offset + target.size]
    return _convert_static(payload, params)
