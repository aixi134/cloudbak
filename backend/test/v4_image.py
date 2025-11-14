import base64
import struct
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Util import Padding

from app.services.decode_wx_pictures import decrypt_file
from test.decrypt import decrypt_dat, decrypt_dat_v3
from wx.win.v4.wxgf_dat2img import decode_wxgf

# 图片的特征码
tp = {
    "jpg": 0xFFD8,
    "gif": 0x4749,
    "png": 0x8950,
}


def print_file_header(file_path, num_bytes=100):
    with open(file_path, "rb") as f:
        header = f.read(num_bytes)
    print(" ".join(f"{b:02X}" for b in header))
    return header


def xor_decrypt(file_path, output_path, key):
    with open(file_path, "rb") as f:
        data = f.read()

    key_bytes = key.to_bytes(4, 'little')  # 变换密钥为字节数组（尝试 'big' 也可以）
    decrypted_data = bytearray()

    # 尝试从第 0 个字节或 10 个字节后开�?
    for i in range(len(data)):
        decrypted_byte = data[i] ^ key_bytes[i % 4]  # 轮流 XOR 4 字节
        decrypted_data.append(decrypted_byte)

    with open(output_path, "wb") as f:
        f.write(decrypted_data)

    print(f"解密完成，输出文�? {output_path}")


def decrypt_image(input_path: str, output_path: str):
    """
    读取加密的图片文件，执行两次异或解密，并保存解密后的图片�?

    :param input_path: 加密图片文件的路�?
    :param output_path: 解密后保存的图片文件路径
    """
    try:
        with open(input_path, 'rb') as enc_file:
            encrypted_data = enc_file.read()

        # 进行两次异或操作解密
        decrypted_data = bytes((byte ^ 0x3C) ^ 0x01 for byte in encrypted_data)

        with open(output_path, 'wb') as dec_file:
            dec_file.write(decrypted_data)

        print(f"解密完成，已保存�?{output_path}")
    except Exception as e:
        print(f"解密失败: {e}")


def decrypt_image_v4(key: bytearray, input_path: str, output_path: str):
    """
    读取加密的图片文件，执行两次异或解密，并保存解密后的图片�?

    :param input_path: 加密图片文件的路�?
    :param output_path: 解密后保存的图片文件路径
    """
    try:
        with open(input_path, 'rb') as enc_file:
            encrypted_data = enc_file.read()

        # 进行两次异或操作解密
        decrypted_data = bytes((byte ^ 0x3C) ^ 0x01 for byte in encrypted_data)

        with open(output_path, 'wb') as dec_file:
            dec_file.write(decrypted_data)

        print(f"解密完成，已保存�?{output_path}")
    except Exception as e:
        print(f"解密失败: {e}")


def xor_decrypt_new(data, key):
    key_bytes = key.to_bytes((key.bit_length() + 7) // 8, 'big')  # 转换为字节数�?
    key_len = len(key_bytes)
    return bytes(data[i] ^ key_bytes[i % key_len] for i in range(len(data)))


def get_image_type(header):
    # 根据文件头判断图片类�?
    if header.startswith(b'\xFF\xD8'):
        return 'jpeg'
    elif header.startswith(b'\x89PNG'):
        return 'png'
    elif header[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    elif header.startswith(b'BM'):
        return 'bmp'
    elif header.startswith(b'\x00\x00\x01\x00'):
        return 'ico'
    elif header.startswith(b'\x49\x49\x2A\x00') or header.startswith(b'\x4D\x4D\x00\x2A'):
        return 'tiff'
    elif header.startswith(b'RIFF') and header[8:12] == b'WEBP':
        return 'webp'
    else:
        return 'png'


def decrypt_dat_v4(input_path: str | Path, xor_key: int, aes_key: bytes) -> bytes:
    """
    解密 v4 版本�?.dat 文件�?
    """
    with open(input_path, "rb") as f:
        header, data = f.read(0xF), f.read()
        signature, aes_size, xor_size = struct.unpack("<6sLLx", header)
        aes_size += AES.block_size - aes_size % AES.block_size

        aes_data = data[:aes_size]
        raw_data = data[aes_size:]

    cipher = AES.new(aes_key, AES.MODE_ECB)
    decrypted_data = Padding.unpad(cipher.decrypt(aes_data), AES.block_size)

    if xor_size > 0:
        raw_data = data[aes_size:-xor_size]
        xor_data = data[-xor_size:]
        xored_data = bytes(b ^ xor_key for b in xor_data)
    else:
        xored_data = b""

    return decrypted_data + raw_data + xored_data


class WeixinInfo:
    weixin_dir: Path | None = None  # 初始化为 None
    xor_key: int = 150  # 添加默认�?
    aes_key: bytes = b"74bfac6b0767bfc5"  # 添加默认�?


info = WeixinInfo()

def decrypt_wechat_dat(dat_path: str):
    """
    解密微信 .dat 文件，并返回：
    - raw_bytes: 解密后的 bytes
    - ext: 文件扩展名 (".jpg" / ".png" / ".mp4" / None)
    - b64: base64 编码内容
    - version: dat 加密版本
    """

    dat_path = Path(dat_path)
    if not dat_path.exists():
        raise FileNotFoundError(f"文件不存在: {dat_path}")

    # 1. 读取加密版本
    version = decrypt_dat(dat_path)
    print(f"[+] 加密版本: v{version}")

    # 2. 数据头解析（可选，用来调试）
    data = dat_path.read_bytes()
    header_len_byte = data[4]
    first_index = data.find(b'\x00\x00\x00\x01', header_len_byte)
    print(f"[Debug] header_len_byte = 0x{header_len_byte:02X}")
    print(f"[Debug] start-code offset = {first_index}")

    # 3. 根据 version 执行解密
    match version:
        case 0:
            raw = decrypt_dat_v3(dat_path, info.xor_key)
        case 1:
            raw = decrypt_dat_v4(dat_path, info.xor_key, b"74bfac6b0767bfc5")
        case 2:
            raw = decrypt_dat_v4(dat_path, info.xor_key, info.aes_key)
        case _:
            raise ValueError(f"不支持的 dat 加密版本: {version}")

    # 4. 处理 WxGF 文件格式
    ext = None
    if raw.startswith(b"wxgf"):  # WxGF wrapper
        print("[+] WxGF 文件，尝试转换...")
        try:
            raw, ext = decode_wxgf(raw)
            print(f"[+] WxGF 转换成功，推断文件类型: {ext}")
        except Exception as exc:
            print(f"[!] WxGF 转换失败: {exc}")

    # 5. 生成 base64
    b64 = base64.b64encode(raw).decode("utf-8")

    return b64
    # return {
    #     "version": version,
    #     "raw_bytes": raw,
    #     "ext": ext,
    #     "base64": b64
    # }
if __name__ == '__main__':

    # 0x104AA022
    dat_path = (
        'D:\\wechat\\xwechat_files\\wxid_7jo9da638dml22_2d5d\\msg\\attach\\9833ce9218f48fbd32eb48beb505d7b0\\2025-11\\Img\\2b1ef911ce3c6e4e1fefad7f9840af6d.dat')


    print(decrypt_wechat_dat(dat_path))
    # decrypt_dat(dat_path)
    # header = print_file_header(dat_path)
    # img_type = get_image_type(header)

    # print(f"推测的图片类型是: {img_type}")

    # dat_path = 'D:\\微信文件\\xwechat_files\\wxid_x1j6ne5cnl8r19_4e0d\\msg\\attach\d31638f7b62b99ff7245e692b150655d\\2025-02\\Img\\d29c797435a3cccba70f3f6c413888ab_t.dat'
    # print_file_header(dat_path)
    # # 0x10B52E
    # dat_path = 'D:\\微信文件\\xwechat_files\\wxid_x1j6ne5cnl8r19_4e0d\\msg\\attach\\d03607872ee740aa9d4eee630fb6c617\\2025-02\\Img\\1b3d18c6ff37cfc8ef4b265294e730cc.dat'
    # print_file_header(dat_path)
    # dat_path = 'D:\\微信文件\\xwechat_files\\wxid_x1j6ne5cnl8r19_4e0d\\msg\\attach\\d03607872ee740aa9d4eee630fb6c617\\2025-02\\Img\\1b3d18c6ff37cfc8ef4b265294e730cc_t.dat'
    # print_file_header(dat_path)
    # # 0x10B33B
    # dat_path = 'D:\\微信文件\\xwechat_files\\wxid_x1j6ne5cnl8r19_4e0d\\msg\\attach\\d03607872ee740aa9d4eee630fb6c617\\2025-02\\Img\\af69f7609d32ed39e653ac091034c4ae.dat'
    # print_file_header(dat_path)
    # dat_path = 'D:\\微信文件\\xwechat_files\\wxid_x1j6ne5cnl8r19_4e0d\\msg\\attach\\d03607872ee740aa9d4eee630fb6c617\\2025-02\\Img\\af69f7609d32ed39e653ac091034c4ae_t.dat'
    # print_file_header(dat_path)
    #
    # key = 0x104AA022
    # input_path = 'C:\\Users\\13448\\xwechat_files\\wxid_7jo9da638dml22_2d5d\\msg\\attach\\9833ce9218f48fbd32eb48beb505d7b0\\2025-11\\Img\\6da1d08a20d476246ee1edcb472980bb.dat'
    # out_path = './6da1d08a20d476246ee1edcb472980bb.png'
    # xor_decrypt(dat_path, out_path, key)

    # # 0x10A4A022
    # print('0x10A4A022')
    # input_path = 'D:\\微信文件\\xwechat_files\\wxid_x1j6ne5cnl8r19_4e0d\\msg\\attach\\d31638f7b62b99ff7245e692b150655d\\2025-02\\Img\\d29c797435a3cccba70f3f6c413888ab.dat'
    # print_file_header(input_path)
    #
    # key = 0x10A4A022
    # with open(input_path, 'rb') as enc_file:
    #     encrypted_data = enc_file.read()
    #     data = xor_decrypt_new(encrypted_data, key)
    #     print(data[:100])

    # key = 0x10A4A022
    # data = decrypt_image(input_path, input_path)
    # # 0x10B52E
    # print('0x10B52E')
    # input_path = 'D:\\微信文件\\xwechat_files\\wxid_x1j6ne5cnl8r19_4e0d\\msg\\attach\d03607872ee740aa9d4eee630fb6c617\\2025-02\\Img\\1b3d18c6ff37cfc8ef4b265294e730cc.dat'
    # print_file_header(input_path)
    # output_path = 'D:/test/6cc1fa07322d7a0420a457df00d00da6_t.jpg'
    # decrypt_image(input_path, output_path)
    # print_file_header(output_path)

    md5 = 'f1bc881c4c678f066f6ecfcd27270505'

