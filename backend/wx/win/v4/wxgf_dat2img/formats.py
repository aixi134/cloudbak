from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Format:
    header: bytes
    ext: str
    aes_key: Optional[bytes] = None


JPG = Format(header=b"\xFF\xD8\xFF", ext="jpg")
PNG = Format(header=b"\x89PNG", ext="png")
GIF = Format(header=b"GIF8", ext="gif")
TIFF = Format(header=b"\x49\x49\x2A\x00", ext="tiff")
BMP = Format(header=b"BM", ext="bmp")
WXGF = Format(header=b"wxgf", ext="wxgf")

V4_FORMATS = [
    Format(header=b"\x07\x08V1", ext="dat", aes_key=b"cfcd208495d565ef"),
    Format(header=b"\x07\x08V2", ext="dat", aes_key=b"0000000000000000"),
]

COMMON_FORMATS = [JPG, PNG, GIF, TIFF, BMP, WXGF]
