import array

import os

from sqlalchemy import inspect, select, func, literal_column

from app.enum.msg_enum import FilterMode
from config.log_config import logger
import xmltodict

from wx.common.filters.msg_filter import MsgFilterObj, SingleMsgFilterObj
from wx.common.output.message import MsgSearchOut, Msg, WindowsV4Properties
from wx.interface.wx_interface import MessageManager, ClientInterface
from wx.win.v4.enums.v4_enums import V4DBEnum
from wx.win.v4.models.message_model import DynamicModel, Name2Id
import zstandard as zstd

from wx.win.v4.utils.zstandard_utils import ZstandardUtils
from wx.win.v4.wechatmsg_utils import (
    parse_image_filename,
    build_image_path_candidates,
    build_thumb_path,
    pick_existing_path,
)


class MessageManagerWindowsV4(MessageManager):

    def __init__(self, client: ClientInterface):
        self.client = client
        self.dynamic = DynamicModel()
        # username 映射的 db 库
        self.user_db_mapping = {}
        self.message_db_name_array = []
        self.resource_manager = client.get_resource_manager()

    def clear(self):
        self.user_db_mapping.clear()
        self.message_db_name_array.clear()

    def get_message_db_name_array(self):
        """
        获取并缓存message库文件列表
        """
        if not self.message_db_name_array:
            self.message_db_name_array = self.client.get_db_manager().messages_db_name_array()
        return self.message_db_name_array

    def get_message_engine_by_db_name(self, db_name: str):
        db_path = f"{V4DBEnum.MESSAGE_DB_FOLDER}/{db_name}"
        return self.client.get_db_manager().wx_db_engine(db_path)

    def get_message_session_maker_by_db_name(self, db_name: str):
        db_path = f"{V4DBEnum.MESSAGE_DB_FOLDER}/{db_name}"
        return self.client.get_db_manager().wx_db(db_path)

    def get_table_name_db_list(self, username: str, table_name: str):
        """
        获取table_name存在的db列表
        """
        array = self.get_message_db_name_array()
        # 存在缓存，直接返回
        if table_name in self.user_db_mapping:
            return self.user_db_mapping[table_name]
        # 不存在缓存，遍历 message_\d.db，检查是否存在表名
        user_db_names = []
        for filename in array:
            engine = self.get_message_engine_by_db_name(filename)
            inspector = inspect(engine)
            if inspector.has_table(table_name):
                logger.info(f"{filename} 中存在 {table_name}")
                user_db_names.append(filename)
        # 按 create_time 排序
        user_db_names = self.sort_db_by_table_name(username, user_db_names)
        # 缓存 username -> [message_\d.db]
        self.user_db_mapping[table_name] = user_db_names
        return user_db_names

    def sort_db_by_table_name(self, username: str, db_array):
        """
        将 db 按照 table_name create_time 时间倒排序
        """
        logger.info(f"原始排序 {db_array}")
        message_model = DynamicModel.get_dynamic_message_model(username)
        create_time_array = []
        for db_name in db_array:
            logger.info(f"库名：{db_name}")
            sm = self.get_message_session_maker_by_db_name(db_name)
            with sm() as db:
                msg = db.query(message_model).order_by(message_model.create_time.desc()).first()
                if msg:  # 只有查询到消息时才加入排序
                    create_time_array.append({
                        "db_name": db_name,
                        "create_time": msg.create_time
                    })
        create_time_array.sort(key=lambda x: x["create_time"], reverse=True)
        final_array = []
        for o in create_time_array:
            final_array.append(o["db_name"])

        logger.info(f"最终排序 {final_array}")
        return final_array

    def messages_filter_page(self, filter_obj: MsgFilterObj) -> MsgSearchOut:
        # 获取动态表
        message_model = DynamicModel.get_dynamic_message_model(filter_obj.username)
        # 获取动态表名
        table_name = message_model.__tablename__
        logger.info(table_name)
        db_name_array = self.get_table_name_db_list(filter_obj.username, table_name)
        # 跨库分页查询
        left = filter_obj.size  # 剩余查询数量
        offset = filter_obj.start if filter_obj.start else 0  # 查询偏移量，初始为客户端送的值
        is_start = False  # 用于判断查询开始
        current_db = None
        msgs = []  # 返回的消息列表
        db_start = False
        for db_name in db_name_array:
            if not is_start:
                if filter_obj.start_db is None or filter_obj.start_db == '':
                    db_start = True
                elif filter_obj.start_db == db_name:
                    db_start = True
            if not db_start:
                logger.info(f"跳过库：{db_name}")
                continue
            current_db = db_name
            logger.info(f"查询库 {db_name}")
            limit = left
            name2id_subquery = (
                select(
                    literal_column("Name2Id.rowid").label("row_num"),
                    Name2Id.user_name
                ).subquery("b")
            )
            stmt = (
                select(message_model, name2id_subquery)
                .join(name2id_subquery, message_model.real_sender_id == name2id_subquery.c.row_num, isouter=True)
                .offset(offset)
                .limit(limit)
            )
            # 根据查询模式确定排序方向
            if filter_obj.filter_mode == FilterMode.DESC:
                stmt = stmt.order_by(message_model.sort_seq.desc())
            else:
                stmt = stmt.order_by(message_model.sort_seq.asc())

            sm = self.get_message_session_maker_by_db_name(db_name)
            with sm() as db:
                results = db.execute(stmt).all()
                for row in results:
                    m = row[0]
                    n = row[2] if len(row) == 3 else None
                    msg = WindowsV4Properties(**m.__dict__)
                    msg.sender = n
                    msg.message_content_data = ZstandardUtils.convert_zstandard(m.message_content)
                    msg.source_data = ZstandardUtils.convert_zstandard(m.source)
                    msg.compress_content_data = ZstandardUtils.convert_zstandard(m.compress_content)
                    self._append_media_info(filter_obj.username, msg, m.packed_info_data, msg.message_content_data)
                    # msg.packed_info_data_data = convert_zstandard(m.packed_info_data)
                    # msg.packed_info_data_data = m.packed_info_data
                    msgs.append(Msg(windows_v4_properties=msg))

                # 判断查询结果数量
                data_count = len(results)
                logger.info(f"预期 {limit}, 实际 {data_count}")
                left = left - data_count
                offset = offset + limit
                logger.info(f"剩余 {left}")
                if left <= 0:
                    logger.info("查询结束")
                    break
                else:
                    offset = 0
            logger.info(db_name)
        return MsgSearchOut(start=offset, start_db=current_db, messages=msgs)

    def message(self, filter_obj: SingleMsgFilterObj) -> Msg | None:
        # 获取动态表
        message_model = DynamicModel.get_dynamic_message_model(filter_obj.username)
        # 获取动态表名
        table_name = message_model.__tablename__
        logger.info(table_name)

        sm = self.get_message_session_maker_by_db_name(filter_obj.db_name)
        with sm() as db:
            msg = db.query(message_model).filter(message_model.local_id.is_(filter_obj.local_id)).one()
            logger.info(f"msg is : {msg}")
        with open('d:/packed_info_data', 'wb') as f:
            f.write(msg.packed_info_data)
        return None

    def _append_media_info(self, talker_username, msg: WindowsV4Properties, packed_bytes: bytes, content_xml: str):
        """
        复用 WeChatMsg 的图片解析思路，补充图片类型的相对路径，便于前端直接显示。
        """
        if msg.local_type != 3:
            return

        file_name = parse_image_filename(packed_bytes)
        candidates = build_image_path_candidates(talker_username, msg.create_time or 0, file_name)
        if not candidates:
            return

        wx_dir = self.client.get_wx_dir()
        session_rel = self._wrap_session_relative(pick_existing_path(wx_dir, candidates))
        thumb_candidate = build_thumb_path(talker_username, msg.create_time or 0, file_name)
        thumb_rel = None
        if thumb_candidate:
            thumb_rel = self._wrap_session_relative(
                pick_existing_path(wx_dir, [thumb_candidate])
            )

        xml_md5 = None
        try:
            if content_xml:
                xml_dict = xmltodict.parse(content_xml)
                xml_md5 = xml_dict.get("msg", {}).get("img", {}).get("@md5")
        except Exception as exc:
            logger.debug(f"parse image xml failed: {exc}")

        if session_rel:
            msg.media = {
                "type": "image",
                "source": session_rel,
                "thumb": thumb_rel or session_rel,
                "file_name": file_name,
                "md5": xml_md5,
            }

    def _wrap_session_relative(self, rel_path_from_wx):
        if not rel_path_from_wx:
            return None
        relative = os.path.join(self.client.get_sys_session().wx_id, rel_path_from_wx)
        return relative.replace("\\", "/")
