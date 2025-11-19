from __future__ import annotations

import os
from typing import Dict, List

START_CODE_LONG = b"\x00\x00\x00\x01"
START_CODE_SHORT = b"\x00\x00\x01"
# HEVC slice NALU types (TRAIL_N .. CRA_NUT) 需要进行 slice header 修复
SLICE_NAL_TYPES = set(range(0, 22))
DEBUG = bool(int(os.environ.get('WXGF_DEBUG', '0')))


def split_annexb(data: bytes) -> List[bytes]:
    nalus: List[bytes] = []
    i = 0
    start = None
    while i < len(data):
        if data.startswith(START_CODE_LONG, i):
            if start is not None:
                nalus.append(data[start:i])
            start = i + len(START_CODE_LONG)
            i = start
        elif data.startswith(START_CODE_SHORT, i):
            if start is not None:
                nalus.append(data[start:i])
            start = i + len(START_CODE_SHORT)
            i = start
        else:
            i += 1
    if start is not None and start < len(data):
        nalus.append(data[start:])
    return [n for n in nalus if n]


def nal_type(nalu: bytes) -> int:
    if not nalu:
        return -1
    return (nalu[0] >> 1) & 0x3F


def is_parameter_set(nt: int) -> bool:
    return nt in {32, 33, 34}


def collect_parameter_sets(chunks: List[bytes]) -> Dict[int, List[bytes]]:
    params: Dict[int, List[bytes]] = {32: [], 33: [], 34: []}
    for chunk in chunks:
        for nalu in split_annexb(chunk):
            nt = nal_type(nalu)
            if nt in params and nalu not in params[nt]:
                params[nt].append(nalu)
    return params


def ensure_parameter_sets(data: bytes, params: Dict[int, List[bytes]]) -> bytes:
    if not params:
        return data
    nalus = split_annexb(data)
    has_vps = any(nal_type(n) == 32 for n in nalus)
    has_sps = any(nal_type(n) == 33 for n in nalus)
    has_pps = any(nal_type(n) == 34 for n in nalus)
    if has_vps and has_sps and has_pps:
        return data
    prefix = bytearray()
    for nt in (32, 33, 34):
        if (nt == 32 and has_vps) or (nt == 33 and has_sps) or (nt == 34 and has_pps):
            continue
        for nalu in params.get(nt, []):
            prefix += START_CODE_LONG + nalu
    if not prefix:
        return data
    return bytes(prefix) + data


def _remove_emulation_prevention(payload: bytes) -> bytes:
    """移除 RBSP 中的 0x000003 防止误判首位标志位。"""
    cleaned = bytearray()
    zero_count = 0
    for byte in payload:
        if zero_count == 2 and byte == 0x03:
            zero_count = 0
            continue
        cleaned.append(byte)
        if byte == 0x00:
            zero_count += 1
        else:
            zero_count = 0
    return bytes(cleaned)


def _first_slice_flag(nalu: bytes) -> bool:
    """解析 slice header 获取 first_slice_segment_in_pic_flag。"""
    if len(nalu) <= 2:
        return False
    rbsp = _remove_emulation_prevention(nalu[2:])
    if not rbsp:
        return False
    return bool(rbsp[0] & 0x80)


def fix_slice_headers(data: bytes) -> bytes:
    """仿照 Go 版本，仅保留首个 slice，并统计重复首帧 slice。"""
    nalus = split_annexb(data)
    if not nalus:
        return data

    fixed_nalus: List[bytes] = []
    first_slice_seen = False
    dropped = 0
    for nalu in nalus:
        nt = nal_type(nalu)
        if nt not in SLICE_NAL_TYPES:
            fixed_nalus.append(nalu)
            continue

        if not first_slice_seen:
            first_slice_seen = True
            fixed_nalus.append(nalu)
            continue

        if not _first_slice_flag(nalu):
            fixed_nalus.append(nalu)
        else:
            dropped += 1

    if DEBUG:
        print(f"[wxgf] hevc slices: total={len(nalus)} dropped_dups={dropped}")

    if len(fixed_nalus) == len(nalus):
        return data

    fixed = bytearray()
    for nalu in fixed_nalus:
        fixed += START_CODE_LONG + nalu
    return bytes(fixed)