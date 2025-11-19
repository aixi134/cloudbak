<script setup>
import defaultImage from '@/assets/default-head.svg';
import AudioPlayer from "../AudioPlayer.vue";
import unknownFile from '@/assets/filetypeicon/unknown.svg';
import cleanedImage from '@/assets/img-cleaned.png';
import {getThumbFromStringContent, fileSize, getReferFileName, fromXmlToJson} from "@/utils/common.js";
import {getContactHeadById} from "@/utils/contact.js";
import {parseMsg} from "@/utils/message_parser_v4.js";
import {get_msg_desc} from "@/utils/msgtp_v4.js";
import {msgBySvrId, singleMsg} from "@/api/msg.js"
import {toBase64} from "js-base64";

import {useStore} from "vuex";
import {computed, reactive} from "vue";
import {getContactById, getContactName} from "../../utils/contact.js";
import MsgTextWithEmoji from "../MsgTextWithEmoji.vue";

const store = useStore();
const emit = defineEmits(['goto-msg']);
const QUOTE_TYPE = 244813135921;
const RED_ENVELOPE_TYPE = 8594229559345;
const PAT_TYPE = 266287972401;
const ANIMATED_EMOJI_TYPE = 47;
const APP_MESSAGE_TYPES = new Set([
  17179869233,
  21474836529,
  12884901937,
  4294967345,
  292057776177,
  326417514545,
  141733920817,
  154618822705,
  103079215153
]);

const props = defineProps({
  roomId: {
    type: String
  },
  msg: {
    type: Object,
    required: true
  },
  chatRoomNameMap: {
    type: Object
  },
  isChatRoom: {
    type: Boolean,
    default: false
  },
  dialogMode: {
    type: Boolean,
    default: false
  }
});

const chatMapBySvrId = reactive({});
const referTypeText = {
  '1': '[文本]',
  '3': '[图片]',
  '34': '[语音]',
  '43': '[视频]',
  '49': '[文件]'
};

/**
 * 设置默认图片
 * @param event
 */
const setDefaultImage = (event) => {
  event.target.src = defaultImage;
}
/**
 * 有备注先用备注，其次群备注，最后昵称
 * @param username
 * @returns {*}
 */
const displayName = (username) => {
  const contact = getContactById(username);
  if (contact) {
    return contact.remark ? contact.remark : contact.nickname;
  }
  let member = props.chatRoomNameMap[username];
  if (member) {
    return member.remark ? member.remark : member.nickname;
  }
  return '未知用户';
}

const headImage = (username) => {
  const contact = getContactById(username);
  if (contact) {
    return contact.small_head_url;
  }
  const member = props.chatRoomNameMap[username]
  if (member) {
    return member.small_head_img;
  }
  return defaultImage;
}

const download = (path) => {
  if (path) {
    path = path.replace('\\', '/');
    const fileName = path.split('/').pop();
    let sessionId = store.getters.getCurrentSessionId;
    let url = `/api/resources/?path=${encodeURIComponent(path)}&session_id=${sessionId}`;
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    // 将<a>元素添加到DOM
    document.body.appendChild(link);
    // 触发点击事件
    link.click();
    // 移除<a>元素
    document.body.removeChild(link);
  }
}

const getOriMsgBySvrId = (svrId, DbNo) => {
  let msg = chatMapBySvrId[svrId];
  // 本地不存在，则到服务端查找
  if (!msg) {
    singleMsg(props.roomId, svrId).then(data => {
      chatMapBySvrId[svrId] = data;
    });
  }
};

if (props.msg.Type === 49 && props.msg.SubType === 19) {
  console.log(props.msg);
}

// 图片代理判断
const getImageUrl = (url) => {
  if (url && typeof url === 'string') {
    if (url.startsWith("/")) {
      return url;
    }
    if (store.getters.isPictureProxy) {
      return `/api/resources-v4/image-proxy?encoded_url=${toBase64(url)}`;
    } else {
      return url;
    }
  }
  return defaultImage;
}

// 解析数据
parseMsg(props.msg)

const isSender = props.msg.sender === store.getters.getCurrentWxId;

const buildRelativeResourceUrl = (relativePath, resourceType = 'image') => {
  if (!relativePath) {
    return undefined;
  }
  // 兼容后端直接返回的 base64 内容（无 data: 前缀）
  if (typeof relativePath === 'string') {
    if (relativePath.startsWith('data:')) {
      return relativePath;
    }
    const isRawBase64 = /^[A-Za-z0-9+/]+={0,2}$/.test(relativePath) && relativePath.length > 100;
    if (isRawBase64) {
      const mime = resourceType === 'video' ? 'video/mp4' : 'image/jpeg';
      return `data:${mime};base64,${relativePath}`;
    }
  }
  const sessionId = store.getters.getCurrentSessionId;
  let url = `/api/resources-v4/relative-resource?relative_path=${encodeURIComponent(relativePath)}&session_id=${sessionId}`;
  if (resourceType === 'video') {
    url += '&resource_type=video';
  }
  return url;
};

const getImageMediaSrc = (media, original = false) => {
  if (!media) {
    return undefined;
  }
  const relative = original ? media.source : (media.thumb || media.source);
  return buildRelativeResourceUrl(relative);
};

const getImageDisplaySrc = (original = false) => {
  if (props.msg.media) {
    return getImageMediaSrc(props.msg.media, original);
  }
  if (props.msg._image) {
    const url = original ? (props.msg._image.originUrl || props.msg._image.thumbUrl) : props.msg._image.thumbUrl;
    return getImageUrl(url);
  }
  return undefined;
};

const isAppMessage = (type) => {
  return APP_MESSAGE_TYPES.has(type);
};

const referContent = (refer) => {
  if (!refer) {
    return '';
  }
  if (refer.contentText) {
    return refer.displayname ? `${refer.displayname}: ${refer.contentText}` : refer.contentText;
  }
  if (refer.type && referTypeText[refer.type]) {
    return `${refer.displayname || ''} ${referTypeText[refer.type]}`.trim();
  }
  return `${refer.displayname || ''} ${refer.content || ''}`.trim();
};

const miniProgramLink = () => {
  if (!props.msg._appmsg) {
    return 'javascript:void(0)';
  }
  if (props.msg._appmsg.url) {
    return props.msg._appmsg.url;
  }
  return 'javascript:void(0)';
};

const getEmojiSrc = () => {
  if (props.msg._emoji?.url) {
    return getImageUrl(props.msg._emoji.url);
  }
  if (props.msg.media && props.msg.media.type === 'image') {
    return getImageMediaSrc(props.msg.media);
  }
  return undefined;
};

const gotoReference = () => {
  const svrId = props.msg._quote?.refer?.svrid;
  if (svrId) {
    emit('goto-msg', svrId);
  }
};

const chatClasses = computed(() => {
  if (!props.dialogMode) {
    return {};
  }
  return {
    right: isSender,
    left: !isSender
  }
});

</script>

<template>
  <div class="chat" :class="chatClasses">
    <div class="chat-header">
      <img :src="headImage(props.msg.sender)" @error="setDefaultImage" alt="" class="exclude"/>
    </div>
    <div class="chat-info">
      <div class="chat-nickname" v-if="props.isChatRoom">
        <p v-if="props.isChatRoom"> {{ displayName(props.msg.sender) }} </p>
      </div>
      <!-- 文本消息 -->
      <div class="chat-text" v-if="props.msg.local_type === 1">
        <msg-text-with-emoji :content="props.msg.data.content"/>
      </div>
      <!-- 图片消息 -->
      <div class="chat-img" v-else-if="getImageDisplaySrc()">

        <img
            class="exclude"
            :src="getImageDisplaySrc()"
            :data-original="getImageDisplaySrc(true)"
            alt="图片"/>
      </div>
      <div class="chat-text" v-else-if="props.msg.local_type === 3">
        [图片消息暂无法加载]
      </div>
      <!-- 动画表情 -->
      <div class="chat-emoji" v-else-if="props.msg.local_type === ANIMATED_EMOJI_TYPE">
        <img v-if="getEmojiSrc()" class="exclude" :src="getEmojiSrc()" alt="表情"/>
        <p class="emoji-desc" v-if="props.msg._emoji?.desc">{{ props.msg._emoji.desc }}</p>
      </div>
<!--       视频消息-->
      <div v-else-if="props.msg.local_type === 43" class="chat-img exclude">
        <video controls width="250" :poster="`/api/resources-v4/video-poster/${store.getters.getCurrentSessionId}/${props.msg._video?.msg.videomsg['@attributes']?.md5}`">
          <source :src="`/api/resources-v4/video/${store.getters.getCurrentSessionId}/${props.msg._video?.msg.videomsg['@attributes']?.md5}`" type="video/mp4" />
        </video>
      </div>
      <!-- 语音 -->
      <div v-else-if="props.msg.local_type === 34" class="chat-media">
        <AudioPlayer
            :src="`/api/resources-v4/media?strUsrName=${props.roomId}&MsgSvrID=${props.msg.server_id}&session_id=${store.getters.getCurrentSessionId}`"
            :text="props.msg.message_content_data || props.msg.data.content"
            :right="isSender"/>
      </div>
      <!-- 引用消息 -->
      <div class="chat-text" v-else-if="props.msg.local_type === QUOTE_TYPE">
        <p>
          {{ props.msg.data.content }}
        </p>
        <div class="refer-msg clickable" v-if="props.msg._quote?.refer" @click="gotoReference">
          <p class="refer-text">
            {{ referContent(props.msg._quote.refer) }}
          </p>
        </div>
      </div>
      <!-- 红包 -->
      <div class="chat-redpacket" v-else-if="props.msg.local_type === RED_ENVELOPE_TYPE">
        <div class="redpacket-left">
          <div class="redpacket-icon" v-if="props.msg._redEnvelope?.iconUrl">
            <img class="exclude" :src="getImageUrl(props.msg._redEnvelope.iconUrl)" alt="红包"/>
          </div>
          <font-awesome-icon v-else class="redpacket-icon redpacket-icon-default" :icon="['fas', 'gift']"/>
        </div>
        <div class="redpacket-body">
          <p class="title">{{ props.msg._redEnvelope?.title || '微信红包' }}</p>
          <p class="desc">点击查看红包</p>
        </div>
        <div class="redpacket-footer">
          <span>微信红包</span>
        </div>
      </div>
      <!-- 拍一拍 -->
      <div class="chat-pat" v-else-if="props.msg.local_type === PAT_TYPE">
        <p>{{ props.msg._pat?.title || props.msg._pat?.template || '拍了拍你' }}</p>
      </div>
      <!-- 小程序 / 卡片 -->
      <a class="chat-appmsg"
         v-else-if="isAppMessage(props.msg.local_type) && props.msg._appmsg"
         :href="miniProgramLink()"
         target="_blank"
         rel="noreferrer">
        <div class="appmsg-cover" v-if="props.msg._appmsg.cover">
          <img class="exclude" :src="getImageUrl(props.msg._appmsg.cover)" alt="cover"/>
        </div>
        <div class="appmsg-body">
          <p class="appmsg-title">{{ props.msg._appmsg.title }}</p>
          <p class="appmsg-desc">{{ props.msg._appmsg.desc }}</p>
          <p class="appmsg-app">{{ props.msg._appmsg.appname || props.msg._appmsg.sourcedisplayname }}</p>
        </div>
      </a>
      <!-- 语音 / 视频通话 -->
      <div class="chat-phone" v-else-if="props.msg.local_type === 50">
        <font-awesome-icon class="icon-file" :icon="['fas', props.msg._voip?.mode === 'video' ? 'video' : 'phone']" title="通话"/>
        {{ props.msg._voip?.text || '[通话记录]' }}
      </div>
      <div class="chat-text" v-else>
        <p>
          [不支持的消息类型: {{get_msg_desc(props.msg.local_type)}}]
        </p>
      </div>

    </div>
  </div>
</template>

<style scoped lang="less">
.chat {
  margin-top: 0.714rem;
  display: flex;
  .chat-header {
    width: 2.5rem;
    height: 2.5rem;
    img {
      width: 2.5rem;
      height: 2.5rem;
      border-radius: 0.214rem;
    }
  }
  .chat-info {
    padding-left: 0.714rem;
    padding-right: 0.714rem;
    .chat-nickname {
      font-size: 0.857rem;
      color: #BEBEBE;
      text-align: left;
    }
    .chat-text {
      direction: ltr;
      font-size: 1rem;
      margin-top: 0.214rem;
      padding: 0.357rem 0.714rem;
      border-radius: 0.357rem;
      display: inline-block;
      color: #232323;
      word-wrap: break-word;
      max-width: 28.571rem;
    }
    .chat-text:hover {
      background-color: #EBEBEB;
    }
    .chat-img {
      direction: ltr;
      word-break: break-word;
      border-radius: 0.286rem;
      img {
        max-width: 14.286rem;
      }
    }
    .chat-img:hover {
      cursor: pointer;
    }
    .chat-media {

    }
    .refer-msg {
      margin-top: 0.357rem;
      direction: ltr;
      .refer-text {
        direction: ltr;
        font-size: 0.857rem;
        background-color: #E8E8E8;
        color: #797979;
        padding: 0.357rem;
        border-radius: 0.214rem;
        display: inline-block;
        max-width: 28.571rem;
        // 长文本换行
        word-wrap: break-word;
        word-break: break-all;
        .icon-file {
          color: #207346;
        }
      }
      .refer-img {
        font-size: 0.857rem;
        background-color: #E8E8E8;
        color: #797979;
        padding: 0.357rem 0.714rem;
        border-radius: 0.214rem;
        display: inline-block;
        word-break: break-word;
      }
    }
    .chat-file {
      height: 8.343rem;
      background-color: #FFFFFF;
      border-radius: 0.357rem;
      .chat-file-top {
        height: 5.357rem;
        border-bottom: 0.071rem solid #f0f0f0;
        display: flex;
        padding: 0.714rem;
        .chat-file-left {
          width: 16.429rem;
          height: 100%;
          .chat-file-title {
            font-size: 1rem;
          }
          .chat-file-content {
            font-size: 0.857rem;
            color: #797979;
            align-items: center;
          }
        }
        .chat-file-icon {
          width: 3.571rem;
          height: 100%;
          font-size: 2.143rem;
          text-align: center;
          color: #207346;
          .item-icon {
            width: 2.857rem;
          }
        }
      }
      .chat-file-bottom {
        .chat-file-app-info {
          font-size: 0.786rem;
          color: #797979;
          padding-left: 0.714rem;
          line-height: 1.786rem;
        }
      }
    }
    .chat-file:hover {
      cursor: pointer;
    }
    .chat-phone {
      background-color: #FFFFFF;
      border-radius: 3px;
      padding:5px 10px;
    }
  }
}
.chat:last-child {
  margin-bottom: 1.429rem;
}
.chat.right {
  .chat-info {
    .chat-nickname {
      text-align: right;
    }
    .chat-text {
      text-align: left;
      background-color: #95ec69;
    }
    .chat-phone {
      background-color: #95ec69;
    }
  }
}
.chat.left {
  flex-direction: row-reverse;
  .chat-info {
    text-align: left;
    .chat-nickname {
      text-align: left;
    }
    .chat-text {
      text-align: left;
      background-color: #FFFFFF;
    }
    .chat-media {
      direction: ltr;
    }
    .chat-phone {
      direction: ltr;
    }
  }
}
.chat.right .chat-info:hover {
  .chat-text {
    background-color: #89D961;
  }
}
.chat.left .chat-info:hover {
  .chat-text {
    background-color: #ebebeb;
  }
}

.chat-emoji {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  img {
    max-width: 8rem;
    max-height: 8rem;
    width: auto;
    height: auto;
    object-fit: contain;
  }
  .emoji-desc {
    margin-top: 0.357rem;
    font-size: 0.857rem;
    color: #777;
  }
}

.chat-redpacket {
  width: 16.429rem;
  border-radius: 0.571rem;
  padding: 0.714rem;
  background: linear-gradient(135deg, #f04d2d, #f26b1f);
  color: #fff7e6;
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  gap: 0.857rem;
  box-shadow: 0 6px 18px rgba(240, 77, 45, 0.35);
  .redpacket-left {
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .redpacket-icon,
  .redpacket-icon-default {
    width: 3.143rem;
    height: 3.143rem;
    border-radius: 50%;
    background-color: rgba(255, 255, 255, 0.2);
    display: flex;
    align-items: center;
    justify-content: center;
    color: #fff7e6;
    font-size: 1.286rem;
    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      border-radius: 50%;
    }
  }
  .redpacket-body {
    flex: 1;
    .title {
      font-size: 1rem;
      font-weight: 600;
      color: #fff;
    }
    .desc {
      font-size: 0.857rem;
      margin-top: 0.214rem;
      color: rgba(255, 255, 255, 0.85);
    }
  }
  .redpacket-footer {
    position: absolute;
    right: 0.857rem;
    bottom: 0.357rem;
    font-size: 0.714rem;
    opacity: 0.8;
  }
}

.chat.right .chat-redpacket {
  background: linear-gradient(135deg, #f6a449, #fbd084);
  color: #442400;
  .redpacket-icon,
  .redpacket-icon-default {
    background-color: rgba(255, 255, 255, 0.35);
    color: #442400;
  }
  .redpacket-footer {
    color: rgba(68, 36, 0, 0.6);
  }
}

.chat-pat {
  background-color: #fff6f0;
  border: 1px solid #ffd8c2;
  border-radius: 0.357rem;
  padding: 0.5rem 0.857rem;
  width: fit-content;
  color: #c95c2c;
}
.refer-msg.clickable {
  cursor: pointer;
}
.chat-appmsg {
  display: block;
  width: 18.571rem;
  padding: 0.714rem;
  background-color: #FFFFFF;
  border: 1px solid #EDEDED;
  border-radius: 0.357rem;
  color: #232323;
  text-decoration: none;
  .appmsg-cover {
    width: 100%;
    height: 8.571rem;
    margin-bottom: 0.357rem;
    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      border-radius: 0.214rem;
    }
  }
  .appmsg-title {
    font-size: 1rem;
    font-weight: 600;
  }
  .appmsg-desc {
    font-size: 0.857rem;
    color: #757575;
    margin-top: 0.214rem;
  }
  .appmsg-app {
    font-size: 0.786rem;
    color: #a8a8a8;
    margin-top: 0.286rem;
  }
}
</style>
