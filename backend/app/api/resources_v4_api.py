import base64
import io
import os
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

from app.enum.resource_enum import ResourceType
from app.schemas.schemas import ContactHeadImgUrlOut
from app.services.decode_wx_pictures import decrypt_file, decrypt_file_return_io
from config.log_config import logger
from wx.client_factory import ClientFactory
from wx.common.filters.msg_filter import SingleMsgFilterObj

from test.v4_image import decrypt_wechat_dat
import base64
import io
from fastapi.responses import StreamingResponse
import mimetypes

router = APIRouter(
    prefix="/resources-v4"
)

def base64_preview(base64_str: str, file_ext: str):
    """
    将 base64 转换为在线预览文件（StreamingResponse）。
    file_ext 例子: ".jpg" ".png" ".mp4" ".pdf"
    """

    # 去掉头部 data:image/jpeg;base64,
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]

    raw_bytes = base64.b64decode(base64_str)

    # 自动 MIME
    mime_type, _ = mimetypes.guess_type("file" + file_ext)
    if mime_type is None:
        mime_type = "application/octet-stream"

    # 内存流
    stream = io.BytesIO(raw_bytes)

    return StreamingResponse(stream, media_type=mime_type)



@router.get("/relative-resource")
async def relative_resource(
        relative_path: str,
        session_id: int,
        resource_type: Optional[ResourceType] = ResourceType.IMAGE):
    client = ClientFactory.get_client_by_id(session_id)
    if client is None:
        logger.info(f"client {session_id} is not exists")
        raise HTTPException(status_code=404, detail="File not found")
    base_dir = client.get_session_dir()
    # base_dir = "D:/wechat/xwechat_files/wxid_7jo9da638dml22_2d5d"
    relative_path = relative_path.replace("\\", '/')
    file_path = os.path.join(base_dir, relative_path)
    # base_dir = Path(r"D:\py-work\cloudbak\backend\data\sessions\1")
    # file_path = base_dir / relative_path.strip("\\/")
    logger.info(f"file_path = {file_path}")
    # 确保 file_path 是 base_dir 的子路径
    abs_file_path = os.path.abspath(file_path)
    abs_base_dir = os.path.abspath(base_dir)
    if not abs_file_path.startswith(abs_base_dir):
        raise HTTPException(status_code=403, detail="Invalid path")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")


    b64 = decrypt_wechat_dat(file_path)
    # b64 可能是 data URI，也可能是纯 base64，统一转为二进制流返回正确的 Content-Type
    if b64.startswith("data:"):
        header, payload = b64.split(",", 1)
        # data:image/jpeg;base64,xxxx
        try:
            mime = header.split(":")[1].split(";")[0]
        except Exception:
            mime = "application/octet-stream"
        raw_bytes = base64.b64decode(payload)
    else:
        # 默认按图片处理
        mime = "image/jpeg" if resource_type == ResourceType.IMAGE else "application/octet-stream"
        raw_bytes = base64.b64decode(b64)
    return StreamingResponse(io.BytesIO(raw_bytes), media_type=mime)




@router.get("/media")
async def get_media(
        strUsrName: str,
        MsgSvrID: str,
        session_id: int,
        db_no: int = 0):
    client = ClientFactory.get_client_by_id(session_id)
    resource_manager = client.get_resource_manager()
    file_path = resource_manager.get_media_path(strUsrName, MsgSvrID)
    if file_path:
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")


@router.get("/image-proxy", response_model=Optional[ContactHeadImgUrlOut])
async def get_head_image(encoded_url: str, request: Request):
    """
        图片代理接口，用于请求 Base64 编码的图片 URL，并将图片数据返回给调用方。

        参数:
        - encoded_url: Base64 编码的图片 URL。
        """
    # 解码 Base64 URL
    try:
        decoded_url = base64.b64decode(encoded_url).decode("utf-8")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid Base64 URL")

    # 使用 httpx 请求图片数据
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(decoded_url)
            response.raise_for_status()
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"Error fetching the image: {e}")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail="Error from the image server")

    # 确保返回的是图片内容
    content_type = response.headers.get("Content-Type", "")

    # 将图片数据流返回给调用方
    return StreamingResponse(
        BytesIO(response.content),
        media_type=content_type
    )


@router.get("/video-poster/{session_id}/{md5}")
async def get_video_thumb(md5: str, session_id: int):
    """
    根据 md5获取 video 封面图
    """
    client = ClientFactory.get_client_by_id(session_id)
    resource_manager = client.get_resource_manager()
    path = resource_manager.get_video_poster(md5, 1763202684)
    if not path:
        raise HTTPException(status_code=404, detail="file not found")
    if not os.path.exists(path):
        logger.warn(f"poster path is not exists: {path}")
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path)


@router.get("/video/{session_id}/{md5}")
async def get_video_thumb(md5: str, session_id: int):
    """
    根据 md5获取 video
    """
    client = ClientFactory.get_client_by_id(session_id)
    resource_manager = client.get_resource_manager()
    path = resource_manager.get_video(md5, 1763202684)
    if not path:
        raise HTTPException(status_code=404, detail="file not found")
    if not os.path.exists(path):
        logger.warn(f"poster path is not exists: {path}")
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path)


@router.get("/resource-from-source-id/{session_id}/{msg_svr_id}/{local_id}")
async def get_image_from_source_id(msg_svr_id: int, session_id: int,local_id: int, file_type: str = 'Thumb', username: Optional[str] = None):
    """
    缩略图、图片、视频文件
    :param username:
    :param msg_svr_id: Multi/MSG.db -> MSG 表的 MsgSvrId
    :param session_id: 会话id
    :param file_type: Thumb-缩略图，Image-原图，Video-视频
    """

    client = ClientFactory.get_client_by_id(session_id)
    message_manager = client.get_message_manager()
    msgFilterObj = SingleMsgFilterObj(username=username, v3_msg_svr_id=msg_svr_id, local_id=local_id)
    msg = message_manager.message(msgFilterObj)
    if msg is None:
        logger.info(f"未查询到消息 msg_svr_id = {msg_svr_id}")
        raise HTTPException(status_code=404, detail="File not found")
    # 转换 BytesExtra 字段
    session_dir = client.get_session_dir()
    if file_type == 'Thumb':
        relative_path = msg.windows_v3_properties.thumb
    elif file_type == 'Image':
        relative_path = msg.windows_v3_properties.source
    elif file_type == 'Video':
        relative_path = msg.windows_v3_properties.source
    else:
        raise HTTPException(status_code=404, detail="File type not permit")
    if relative_path is None:
        logger.warn("relative path is None")
        raise HTTPException(status_code=404, detail="File not found")
    file_path = os.path.join(session_dir, relative_path)
    logger.info("文件路径：%s", file_path)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    if file_path.endswith('.dat'):
        decrypted_stream = decrypt_file_return_io(file_path)

        if decrypted_stream is None:
            raise HTTPException(status_code=400, detail="Failed to decrypt the file")

        # 返回解密后的字节流数据
        return StreamingResponse(decrypted_stream, media_type="image/jpeg")
    else:
        def iter_file():
            """以块形式读取文件，生成器实现流式返回"""
            with open(file_path, "rb") as file:
                while chunk := file.read(1024 * 1024):  # 每次读取 1MB
                    yield chunk
        return StreamingResponse(iter_file(), media_type="video/mp4")
