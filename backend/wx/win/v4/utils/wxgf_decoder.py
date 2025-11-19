"""Backward-compatible entry point for wxgf decoding."""
from __future__ import annotations

from wx.win.v4.wxgf_dat2img.decoder import decode_wxgf  # re-export

__all__ = ["decode_wxgf"]
