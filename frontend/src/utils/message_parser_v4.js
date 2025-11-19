import {fromXmlToJson, parseXml} from "@/utils/common.js";

const QUOTE_TYPE = 244813135921;
const APP_MESSAGE_TYPES = [
    17179869233,
    21474836529,
    12884901937,
    4294967345,
    292057776177,
    326417514545,
    141733920817,
    154618822705,
    103079215153
];
const ANIMATED_EMOJI_TYPE = 47;
const RED_ENVELOPE_TYPE = 8594229559345;
const PAT_TYPE = 266287972401;

const parseText = (msg, wx_id) => {
    let data = msg.message_content_data;
    if (data.indexOf(":\n") !== -1) {
        let array = data.split(":\n");
        return {
            sender: array[0],
            content: array[1]
        }
    } else {
        return {
            sender: wx_id,
            content: data
        }
    }
}

export const parseMsg = (msg, wx_id) => {
    msg['data'] = parseText(msg, wx_id);
    if (msg.message_content_data) {
        try {
            msg.message_content = fromXmlToJson(msg.message_content_data);
        } catch (e) {
            console.warn("parse v4 message content failed", e);
        }
    }
    if (msg.compress_content_data) {
        try {
            msg.compress_content = fromXmlToJson(msg.compress_content_data);
        } catch (e) {
            console.warn("parse v4 compress content failed", e);
        }
    }
    if (msg.local_type === 43) {
        if (msg.data.content) {
            msg['_video'] = fromXmlToJson(msg.data.content)
        }
    }
    if (msg.local_type === 50) {
        enrichVoipInfo(msg);
    }
    if (msg.local_type === 3) {
        enrichImageInfo(msg);
    }
    if (msg.local_type === 34) {
        enrichVoiceInfo(msg);
    }
    if (msg.local_type === ANIMATED_EMOJI_TYPE) {
        enrichEmojiInfo(msg);
    }
    if (msg.local_type === RED_ENVELOPE_TYPE) {
        enrichRedEnvelopeInfo(msg);
    }
    if (msg.local_type === PAT_TYPE) {
        enrichPatInfo(msg);
    }
    if (msg.local_type === QUOTE_TYPE) {
        enrichQuoteInfo(msg);
    }
    if (APP_MESSAGE_TYPES.includes(msg.local_type)) {
        enrichAppMessageInfo(msg);
    }
}

const normalizeText = (value) => {
    if (!value) {
        return '';
    }
    if (typeof value === 'string') {
        return value;
    }
    if (Array.isArray(value)) {
        return value.map(normalizeText).join('');
    }
    if (typeof value === 'object') {
        if ('#text' in value) {
            return normalizeText(value['#text']);
        }
        return Object.values(value).map(normalizeText).join('');
    }
    return String(value);
};

const parseAppMsgNode = (msg) => {
    if (msg.message_content?.msg?.appmsg) {
        return msg.message_content.msg.appmsg;
    }
    let parsed = parseXmlToJsonSafe(msg.message_content_data);
    if (parsed?.msg?.appmsg) {
        msg.message_content = parsed;
        return parsed.msg.appmsg;
    }
    if (msg.compress_content?.msg?.appmsg) {
        return msg.compress_content.msg.appmsg;
    }
    parsed = parseXmlToJsonSafe(msg.compress_content_data);
    if (parsed?.msg?.appmsg) {
        msg.compress_content = parsed;
        return parsed.msg.appmsg;
    }
    return null;
};

const parseXmlToJsonSafe = (text) => {
    if (!text) {
        return null;
    }
    try {
        return fromXmlToJson(text);
    } catch (e) {
        console.warn("parse xml to json failed", e);
    }
    return null;
};

const enrichImageInfo = (msg) => {
    if (!msg.message_content_data) {
        return;
    }
    try {
        const dom = parseXml(msg.message_content_data);
        const img = dom?.querySelector('img');
        if (!img) {
            return;
        }
        msg._image = {
            thumbUrl: img.getAttribute('cdnthumburl'),
            originUrl: img.getAttribute('cdnmidimgurl') || img.getAttribute('cdnthumbaeskey'),
            fileKey: img.getAttribute('filekey'),
            md5: img.getAttribute('md5')
        }
    } catch (e) {
        console.warn("parse v4 image xml failed", e);
    }
}

const enrichVoiceInfo = (msg) => {
    if (!msg.message_content_data) {
        return;
    }
    try {
        const dom = parseXml(msg.message_content_data);
        const voice = dom?.querySelector('voicemsg');
        if (!voice) {
            return;
        }
        msg._voice = {
            length: voice.getAttribute('voicelength'),
            format: voice.getAttribute('voiceformat'),
            endFlag: voice.getAttribute('endflag')
        }
    } catch (e) {
        console.warn("parse v4 voice xml failed", e);
    }
}

const enrichQuoteInfo = (msg) => {
    const appmsg = parseAppMsgNode(msg);
    if (!appmsg) {
        return;
    }
    const title = normalizeText(appmsg.title);
    if (title) {
        msg.data.content = title;
    } else if (msg.data?.content) {
        msg.data.content = normalizeText(msg.data.content);
    }
    const refer = appmsg?.refermsg;
    if (refer) {
        const contentText = normalizeText(refer.content);
        msg._quote = {
            refer: {
                type: refer.type,
                content: contentText,
                contentText,
                displayname: normalizeText(refer.displayname),
                svrid: refer.svrid
            }
        }
    }
}

const enrichAppMessageInfo = (msg) => {
    const appmsg = parseAppMsgNode(msg);
    if (!appmsg) {
        return;
    }
    const appinfo = appmsg.appinfo || msg.message_content?.msg?.appinfo;
    const weappinfo = appmsg.weappinfo || {};
    msg._appmsg = {
        title: normalizeText(appmsg.title) || '',
        desc: normalizeText(appmsg.des) || '',
        url: appmsg.url || '',
        cover: appmsg.thumburl || appmsg?.mmreader?.template_header?.icon_url || '',
        appname: normalizeText(appinfo?.appname) || normalizeText(appmsg.sourcedisplayname) || '',
        sourcedisplayname: normalizeText(appmsg.sourcedisplayname) || '',
        weapp: {
            appid: weappinfo['@appid'] || '',
            username: weappinfo['username'] || '',
            pagepath: weappinfo['pagepath'] || '',
            icon: weappinfo['weappiconurl'] || ''
        }
    }
}

const enrichEmojiInfo = (msg) => {
    const xmlSource = msg.message_content_data || msg.data?.content;
    if (!xmlSource) {
        return;
    }
    try {
        const dom = parseXml(xmlSource);
        const emoji = dom?.querySelector('emoji');
        if (!emoji) {
            return;
        }
        msg._emoji = {
            url: emoji.getAttribute('cdnurl'),
            md5: emoji.getAttribute('md5'),
            width: Number(emoji.getAttribute('width') || 0),
            height: Number(emoji.getAttribute('height') || 0),
            desc: normalizeText(emoji.getAttribute('alt') || '')
        };
    } catch (e) {
        console.warn("parse animated emoji failed", e);
    }
};

const enrichRedEnvelopeInfo = (msg) => {
    const appmsg = parseAppMsgNode(msg);
    if (!appmsg || !appmsg.wcpayinfo) {
        return;
    }
    const info = appmsg.wcpayinfo;
    msg._redEnvelope = {
        title: normalizeText(info.receivertitle) || normalizeText(appmsg.title) || '微信红包',
        iconUrl: info.iconurl || '',
        innerType: Number(info.innertype || 0)
    };
};

const enrichPatInfo = (msg) => {
    const appmsg = parseAppMsgNode(msg);
    if (!appmsg) {
        return;
    }
    const patinfo = appmsg.patinfo || {};
    msg._pat = {
        title: normalizeText(appmsg.title) || '',
        template: normalizeText(patinfo.template) || '',
        from: patinfo.fromusername,
        to: patinfo.pattedusername
    };
    if (!msg.data.content) {
        msg.data.content = msg._pat.template || msg._pat.title;
    }
};

const enrichVoipInfo = (msg) => {
    if (!msg.message_content && !msg.message_content_data) {
        return;
    }
    let data = msg.message_content;
    if (!data && msg.message_content_data) {
        try {
            data = fromXmlToJson(msg.message_content_data);
        } catch (e) {
            console.warn("parse v4 voip xml failed", e);
            return;
        }
    }
    const bubbleMsg = data?.voipmsg?.VoIPBubbleMsg?.msg;
    const inviteMsg = data?.voipinvitemsg;
    const displayContent = normalizeText(
        bubbleMsg ||
        inviteMsg?.display_content ||
        data?.voiplocalinfo?.display_content ||
        msg.data?.content
    );
    if (!displayContent) {
        return;
    }
    let mode = 'voice';
    const lower = displayContent.toLowerCase();
    if (lower.includes('视频') || lower.includes('video')) {
        mode = 'video';
    } else if (lower.includes('语音') || lower.includes('voice')) {
        mode = 'voice';
    }
    msg._voip = {
        text: displayContent,
        mode,
        duration: inviteMsg?.duration || data?.voiplocalinfo?.duration || ''
    }
};
