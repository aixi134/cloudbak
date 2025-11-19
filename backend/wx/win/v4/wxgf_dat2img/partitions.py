from __future__ import annotations

from dataclasses import dataclass
from typing import List

PATTERNS = (b"\x00\x00\x00\x01", b"\x00\x00\x01")
MIN_RATIO = 0.6


@dataclass
class Partition:
    offset: int
    size: int
    ratio: float


@dataclass
class PartitionSet:
    partitions: List[Partition]
    max_index: int
    max_ratio: float

    def like_anime(self) -> bool:
        return len(self.partitions) > 1 and self.max_ratio < MIN_RATIO


def find_partitions(data: bytes) -> PartitionSet:
    header_len = data[4]
    if header_len >= len(data):
        raise ValueError("invalid wxgf header")

    for pattern in PATTERNS:
        partitions: List[Partition] = []
        max_ratio = -1.0
        max_index = -1
        offset = 0
        while header_len + offset < len(data):
            search_from = header_len + offset
            idx = data.find(pattern, search_from)
            if idx == -1:
                break
            rel_idx = idx - search_from
            abs_idx = idx
            if abs_idx < 4:
                offset += rel_idx + 1
                continue
            length = int.from_bytes(data[abs_idx - 4 : abs_idx], "big")
            if length <= 0 or abs_idx + length > len(data):
                offset += rel_idx + 1
                continue
            ratio = length / len(data)
            partitions.append(Partition(abs_idx, length, ratio))
            if ratio > max_ratio:
                max_ratio = ratio
                max_index = len(partitions) - 1
            offset += rel_idx + length
        if partitions:
            return PartitionSet(partitions, max_index, max_ratio)
    raise ValueError("no valid partition found")
