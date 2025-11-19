import hashlib
import importlib.util
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional


def _load_proto_module(file_name: str, module_name: str):
    """
    动态加载 WeChatMsg 中的 proto 解析模块，避免引入整个 wxManager 依赖。
    逐层向上查找 WeChatMsg 目录，兼容不同目录深度。
    """
    current_dir = Path(__file__).resolve()
    proto_file = None
    for parent in current_dir.parents:
        candidate = parent / 'WeChatMsg' / 'wxManager' / 'parser' / 'util' / 'protocbuf' / file_name
        if candidate.exists():
            proto_file = candidate
            break
    if proto_file is None:
        return None
    spec = importlib.util.spec_from_file_location(module_name, proto_file)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
_img2_pb2 = _load_proto_module("packed_info_data_img2_pb2.py", "wechatmsg_packed_info_data_img2_pb2")
_img_pb2 = _load_proto_module("packed_info_data_img_pb2.py", "wechatmsg_packed_info_data_img_pb2")


def _sanitize_filename(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return name.strip().strip('"').strip()


def parse_image_filename(packed_bytes: Optional[bytes]) -> Optional[str]:
    """
    解析 packed_info_data，获取图片在本地磁盘上的文件名。
    """
    if not packed_bytes:
        return None

    if _img2_pb2:
        try:
            proto = _img2_pb2.PackedInfoDataImg2()
            proto.ParseFromString(packed_bytes)
            if proto.imageInfo and proto.imageInfo.filename:
                name = _sanitize_filename(proto.imageInfo.filename)
                if name:
                    return name
            if proto.fileInfo and proto.fileInfo.fileInfo and proto.fileInfo.fileInfo.filename:
                name = _sanitize_filename(proto.fileInfo.fileInfo.filename)
                if name:
                    return name
        except Exception:
            pass

    if _img_pb2:
        try:
            proto = _img_pb2.PackedInfoDataImg()
            proto.ParseFromString(packed_bytes)
            if proto.filename:
                return _sanitize_filename(proto.filename)
        except Exception:
            pass
    return None


def build_image_path_candidates(talker_username: str,
                                timestamp: int,
                                filename: Optional[str]) -> List[str]:
    """
    根据聊天对象与时间构造图片可能的相对路径（相对于 wx_dir）。
    """
    if not talker_username:
        return []
    hashed = hashlib.md5(talker_username.encode("utf-8")).hexdigest()
    if timestamp:
        month = datetime.fromtimestamp(timestamp).strftime("%Y-%m")
    else:
        month = datetime.now().strftime("%Y-%m")
    base_dir = Path("msg") / "attach" / hashed / month / "Img"
    if filename:
        stem = Path(filename).stem
    else:
        stem = ""
    candidates = []
    if stem:
        candidates.extend([
            base_dir / f"{stem}_W.dat",
            base_dir / f"{stem}_h.dat",
            base_dir / f"{stem}.dat",
        ])
    else:
        # 兜底未知文件名
        candidates.append(base_dir / f"{int(timestamp)}.dat")
    return [str(path).replace("\\", "/") for path in candidates]


def build_thumb_path(talker_username: str,
                     timestamp: int,
                     filename: Optional[str]) -> Optional[str]:
    if not talker_username:
        return None
    hashed = hashlib.md5(talker_username.encode("utf-8")).hexdigest()
    if timestamp:
        month = datetime.fromtimestamp(timestamp).strftime("%Y-%m")
    else:
        month = datetime.now().strftime("%Y-%m")
    base_dir = Path("msg") / "attach" / hashed / month / "Img"
    if filename:
        stem = Path(filename).stem
        thumb = base_dir / f"{stem}_t.dat"
        return str(thumb).replace("\\", "/")
    return None



def pick_existing_path(wx_dir: str, candidates: List[str]) -> Optional[str]:
    """
    在候选路径中选择一个真实存在的相对路径。
    返回值：
        - 匹配到的相对路径（使用 candidates 中的原始格式）
        - 若都不存在，返回 candidates[0]
        - 若 candidates 为空，返回 None
    """

    if not candidates:
        return None

    # 依次检查候选路径
    for candidate in candidates:
        # 标准化路径（将 "/" 转换为 Windows "\" 和去掉冗余）
        abs_path = os.path.normpath(os.path.join(wx_dir, candidate))

        if os.path.exists(abs_path):
            return candidate   # 返回相对路径，而非绝对路径

    # 若都不存在，返回第一个候选项
    return candidates[0]
