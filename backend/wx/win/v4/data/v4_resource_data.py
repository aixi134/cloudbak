import os
import os.path
import re
import sqlite3

from datetime import datetime
from sqlalchemy import select, func

from config.log_config import logger
from wx.interface.wx_interface import ResourceManager, ClientInterface
from wx.win.v4.enums.v4_enums import V4DBEnum
from wx.win.v4.models.hardlink import Dir2IdModel, Dir2IdModel, VideoHardlinkInfoModelV3, VideoHardlinkInfoModelV4, ImageHardlinkInfoModelV3, ImageHardlinkInfoModelV4
from wx.win.v4.models.head_image import HeadImageModel
from app.services.decode_wx_media import decode_media


class WindowsV4ResourceManager(ResourceManager):

    def __init__(self, client: ClientInterface):
        self.client = client

    def windows_v3_image_from_full_md5(self, full_md5: str, prev: str = 'Thumb'):
        pass

    def get_decode_media_path(self) -> str:
        decode_dir = os.path.join(self.client.get_session_dir(), V4DBEnum.DECODED_MEDIA_PATH)
        if not os.path.exists(decode_dir):
            os.makedirs(decode_dir, exist_ok=True)
        return decode_dir

    def get_media_path(self, username: str, win_v3_msg_svr_id: str) -> str | None:
        try:
            svr_id = int(win_v3_msg_svr_id)
        except (TypeError, ValueError):
            return None
        media_dir = self.get_decode_media_path()
        target_path = os.path.join(media_dir, f"{svr_id}.mp3")
        if os.path.exists(target_path):
            return target_path
        voice_data = self._query_voice_data(svr_id)
        if voice_data is None:
            return None
        return decode_media(media_dir, str(svr_id), voice_data)

    def get_wx_owner_img(self) -> str:
        wx_id = self.client.get_sys_session().wx_id
        logger.info(f"获取头像 {wx_id}")
        relative_path = os.path.join(wx_id, V4DBEnum.HEAD_IMAGE_FOLDER, f"{wx_id}.jpg")
        image_path = os.path.join(self.client.get_wx_dir(), V4DBEnum.HEAD_IMAGE_FOLDER, f"{wx_id}.jpg")
        logger.info(f"头像路径")
        if os.path.exists(image_path):
            logger.info("存在，返回")
            return relative_path
        logger.info("不存在，生成")
        sm = self.client.get_db_manager().wx_db(V4DBEnum.HEAD_IMAGE_DB_PATH)
        with sm() as db:
            real_wx_id = self.client.get_real_wx_id()
            head = db.query(HeadImageModel).filter_by(username=real_wx_id).first()
            if head:
                logger.info("head_image库中存在数据")
                folder = os.path.join(self.client.get_wx_dir(), V4DBEnum.HEAD_IMAGE_FOLDER)
                if not os.path.exists(folder):
                    os.makedirs(folder)
                try:
                    logger.info(f"写入头像 {image_path}")
                    with open(image_path, 'wb') as f:
                        f.write(head.image_buffer)
                    return relative_path
                except Exception as e:
                    logger.error('保存头像错误', e)
        logger.info("head_image库中不存在数据")
        return None
    def _get_table_version(self):
        return 4
    def get_video_poster(self, md5: str, msg_create_time: int) -> str | None:
        # 优先从表中获取
        logger.info("从hardlink表中获取视频封面")
        sm = self.client.get_db_manager().wx_db(V4DBEnum.HARDLINK_DB_PATH)
        dir2id_subquery = (
            select(
                func.row_number().over(order_by=None).label("row_num"),
                Dir2IdModel.username
            ).subquery("b")
        )

        # 获取表版本
        table_version = self._get_table_version()
        logger.info(f"当前hardlink库版本: {table_version}")
        # 根据版本选择对应的模型
        if table_version == 4:
            VideoModel = VideoHardlinkInfoModelV4
        else:
            VideoModel = VideoHardlinkInfoModelV3

        stmt = (
            select(VideoModel, dir2id_subquery)
            .join(dir2id_subquery, VideoModel.dir1 == dir2id_subquery.c.row_num, isouter=True)
            .where(VideoModel.md5.is_(md5))
        )
        with sm() as db:
            row = db.execute(stmt).first()
            if row:
                logger.info(f"hardlink data: {row}")
                hardlink = row[0]
                # row_num = row[1]
                dir_name = row[2]
                name, ext = hardlink.file_name.rsplit('.', 1)
                poster_abs_path = f"{self.client.get_wx_dir()}/msg/video/{dir_name}/{name}.jpg"
                if os.path.exists(poster_abs_path):
                    logger.info(f"poster_abs_path: {poster_abs_path} 不存在")
                    return poster_abs_path
                poster_abs_path = f"{self.client.get_wx_dir()}/msg/video/{dir_name}/{name}_thumb.jpg"
                if os.path.exists(poster_abs_path):
                    logger.info(f"poster_abs_path: {poster_abs_path} 不存在")
                    return poster_abs_path
        logger.info("hardlink表中未找到视频封面")
        # 规则为，优先获取清晰封面图
        # msg/video/月份/{md5}.jpg
        # msg/video/月份/{md5}_thumb.jpg
        month = datetime.fromtimestamp(msg_create_time).strftime('%Y-%m')
        folder = os.path.join(self.client.get_wx_dir(), 'msg', 'video', month)
        poster_name = f"{md5}.jpg"
        poster_abs_path = os.path.join(folder, poster_name)
        logger.info(f"poster_abs_path: {poster_abs_path}")
        if os.path.exists(poster_abs_path):
            logger.info(f"poster_abs_path: {poster_abs_path} 存在")
            return poster_abs_path
        poster_name = f"{md5}_thumb.jpg"
        poster_abs_path = os.path.join(folder, poster_name)
        logger.info(f"poster_abs_path: {poster_abs_path}")
        if os.path.exists(poster_abs_path):
            logger.info(f"poster_abs_path: {poster_abs_path} 存在")
            return poster_abs_path
        logger.info("规则路径中未找到视频封面")
        return None


    def get_video(self, md5: str, msg_create_time: int) -> str | None:
        # 优先从表中获取
        # 获取表版本
        table_version = self._get_table_version()
        logger.info(f"当前hardlink库版本: {table_version}")
        # 根据版本选择对应的模型
        if table_version == 4:
            VideoModel = VideoHardlinkInfoModelV4
        else:
            VideoModel = VideoHardlinkInfoModelV3

        sm = self.client.get_db_manager().wx_db(V4DBEnum.HARDLINK_DB_PATH)
        dir2id_subquery = (
            select(
                func.row_number().over(order_by=None).label("row_num"),
                Dir2IdModel.username
            ).subquery("b")
        )
        stmt = (
            select(VideoModel, dir2id_subquery)
            .join(dir2id_subquery, VideoModel.dir1 == dir2id_subquery.c.row_num, isouter=True)
            .where(VideoModel.md5.is_(md5))
        )
        with sm() as db:
            row = db.execute(stmt).first()
            if row:
                logger.info(f"hardlink data: {row}")
                hardlink = row[0]
                # row_num = row[1]
                dir_name = row[2]
                return f"{self.client.get_wx_dir()}/msg/video/{dir_name}/{hardlink.file_name}"
        logger.info("hardlink表中未找到视频")
        # 规则为，msg/video/月份/{md5}.mp4
        month = datetime.fromtimestamp(msg_create_time).strftime('%Y-%m')
        folder = os.path.join(self.client.get_wx_dir(), 'msg', 'video', month)
        video_name = f"{md5}.mp4"
        video_abs_path = os.path.join(folder, video_name)
        logger.info(f"video_abs_path: {video_abs_path}")
        if os.path.exists(video_abs_path):
            logger.info(f"video_abs_path: {video_abs_path} 存在")
            return video_abs_path
        logger.info("规则路径中未找到视频")
        return None

    def get_member_head(self, username: str) -> bytearray:
        pass

    def _media_db_paths(self):
        message_dir = os.path.join(self.client.get_wx_dir(), V4DBEnum.DB_BASE_PATH, V4DBEnum.MESSAGE_DB_FOLDER)
        if not os.path.exists(message_dir):
            return []
        pattern = re.compile(r'^decoded_media_\d+\.db$')
        dbs = []
        for name in os.listdir(message_dir):
            if pattern.match(name):
                dbs.append(os.path.join(message_dir, name))
        dbs.sort()
        return dbs

    def _query_voice_data(self, svr_id: int):
        for db_path in self._media_db_paths():
            try:
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.execute("SELECT voice_data FROM VoiceInfo WHERE svr_id = ? LIMIT 1", (svr_id,))
                    row = cur.fetchone()
                    if row and row["voice_data"]:
                        return row["voice_data"]
            except Exception as exc:
                logger.warning(f"read voice data failed for {db_path}: {exc}")
        return None
