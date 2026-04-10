"""PIC以外にも使えそうなモノ"""

import io
from typing import BinaryIO, Union

import numpy as np


class ReadError(RuntimeError):
    pass


class BitStream:
    """ビット単位でのread/writeをおこなう

    ※ライフサイクル中にread/writeの混在はできません。

    :var size: 読み書きしたビット数
    """

    def __init__(self, buf: Union[BinaryIO, bytes]):
        if isinstance(buf, bytes):
            buf = io.BytesIO(buf)
        self.buf = buf
        self.size = 0
        self.temp = ""

    def write(self, bits: int, value: int):
        assert value.bit_length() <= bits
        self.temp += f"{value:0{bits}b}"
        self.size += bits
        if len(self.temp) >= 8:
            n = len(self.temp) & -8
            bytes = int(self.temp[:n], base=2).to_bytes(n >> 3)
            self.buf.write(bytes)
            self.temp = self.temp[n:]

    def read(self, bits: int) -> int:
        req_bytes = ((bits - len(self.temp)) + 7) >> 3
        if req_bytes:
            blob = self.buf.read(req_bytes)
            if len(blob) != req_bytes:
                raise ReadError(
                    f"End of file reached. Failed to read required {req_bytes} bytes."
                )
            value = int.from_bytes(blob)
            self.temp += f"{value:0{req_bytes * 8}b}"
        self.size += bits
        part, self.temp = self.temp[:bits], self.temp[bits:]
        return int(part, base=2)

    def flush(self):
        """
        保留中のビット列をバッファへ書き出します
        """
        n = self.size & 7
        if n:
            self.write(8 - n, 0)
        self.buf.flush()

    def write_bytes(self, value: bytes):
        assert self.size & 7 == 0  # バイトアラインを跨ぐのは許さいない
        self.size += self.buf.write(value) * 8

    def read_bytes(self, n: int) -> bytes:
        assert self.size & 7 == 0
        blob = self.buf.read(n)
        self.size += len(blob) * 8
        return blob

    def read_until(self, term: bytes) -> bytes:
        """終端バイトが現れるまでバイト列を読み込む

        :param term: 終端バイト
        :return: 読み出したバイト列。終端(term)は含まない。
        :rtype: bytes
        """
        data = b""
        while True:
            byte = self.read_bytes(1)
            if byte == term:
                break
            data += byte
        return data


class ColorFormat(dict):
    """カラーコードのビットフィールドを扱うヘルパークラス

    チャネル文字をキーとするChannelの辞書(dict)です。

    :var order: チャネルの順序
    :var bits: 各チャネルのビット数
    """

    order: str
    bits: list[int]

    def __init__(self, format: str):
        """カラーフォーマットオブジェクトの初期化

        :param format: カラーフォーマット指定文字列

            各チャネルは 識別1字 + ビット数1字 で表現されます。

            (例) GRB順の12ビットカラー -> "g4r4b4"
        """
        self.order = format[::2]
        self.bits = list(map(int, format[1::2]))

        assert len(self.bits) == len(self.order)
        shift = sum(self.bits)
        for ch, bits in zip(self.order, self.bits):
            mask = (1 << shift) - 1
            shift -= bits
            mask ^= (1 << shift) - 1
            self[ch] = self.Channel(mask, shift, bits)

    class Channel:
        """カラーコード中のチャネル/ビットフィールドを表現する"""

        def __init__(self, mask: int, shift: int, bits: int):
            self.mask = mask
            self.shift = shift
            self.bits = bits
            self.max = (1 << bits) - 1

        def get(self, v):
            return (v & self.mask) >> self.shift

        def put(self, v, inbits=8):
            return ((v >> (inbits - self.bits)) << self.shift) & self.mask


def decode_color(color: np.ndarray, format: str, *, order: str = "rgb") -> np.ndarray:
    """任意のカラーコードをNumPy画像へデコードします

    :param color: カラーコード
    :param format: 入力フォーマット (例: "g5r5b5i1")
    :param order: 出力のR,G,Bの順序 (デフォルト: "rgb")
    :return: デコードされたNumPy画像
    """
    colorf = ColorFormat(format)

    rgb = {ch: field.get(color) / field.max for ch, field in colorf.items()}

    # X68000の輝度ビット
    if "i" in rgb:
        i = rgb["i"]
        u = 1 / (1 << (max(colorf.bits) + 1))
        u = i * u
        v = 1 - u
        for ch in "rgb":
            rgb[ch] = rgb[ch] * u + rgb[ch] * v

    a = np.dstack([rgb[ch] for ch in order])
    a = (a * 255).astype(np.uint8)
    return a


def encode_color(
    im: np.ndarray, format: str, *, order: str = "rgb", dither=False
) -> np.ndarray:
    """NumPy画像を任意のカラーコードへエンコードします

    :param im: 入力画像 (np.ndarray)
    :param format: 出力フォーマット (例: "g5r5b5i1")
    :param order: 入力のR,G,Bの順序 (デフォルト: "rgb")
    :param dither: ディザリングを適用するかどうか (デフォルト: False)
    :return: エンコードされた画像

    Examples
    --------
        ```
        # NumPy画像をX68000/16bitのカラーコードへ変換
        pix = encode_color(cv2.imread("sample.png"), "g5r5b5i1", order="bgr")
        ```
    """
    if im.dtype != np.uint8:
        raise ValueError("image must be uint8")

    colorf = ColorFormat(format)

    bits = sum(colorf.bits)
    channels = np.moveaxis(im, -1, 0)

    rgb = {ch: channels[order.index(ch)] for ch in "rgb"}

    if dither and bits < 24:
        for ch in "rgb":
            rgb[ch] = dither_grayscale(rgb[ch], colorf[ch].bits)

    dtype = np.uint32 if bits > 16 else (np.uint16 if bits > 8 else np.uint8)

    for ch, a in rgb.items():
        rgb[ch] = a.astype(dtype)

    c = (
        colorf["r"].put(rgb["r"])
        | colorf["g"].put(rgb["g"])
        | colorf["b"].put(rgb["b"])
    )

    # X68000の輝度ビット
    # 汎用的な関数にするつもりだったけれどココだけ例外です^^;
    if format.endswith("i1"):
        i = (rgb["r"] & 7) * 0.299
        i += (rgb["g"] & 7) * 0.587
        i += (rgb["b"] & 7) * 0.114
        c |= i > 3.5

    return c


def dither_grayscale(image: np.ndarray, bits: int) -> np.ndarray:
    """8bitグレースケール画像を任意のビット数に量子化し、ディザリングを適用する

    :param image: 入力画像 (np.uint8, 2次元配列)
    :param bits: 目標ビット数 (1〜7)

    :rtype: np.ndarray
    :returns: 量子化・ディザリング後の画像 (0-255の範囲)
    """
    if image.dtype != np.uint8:
        raise ValueError("image must be uint8")
    if image.ndim != 2:
        raise ValueError("image must be grayscale (2D)")
    if not (1 <= bits <= 7):
        raise ValueError("bits must be between 1 and 7")

    # コピーしてfloatで処理
    img = image.astype(np.float32)

    # 量子化レベル数
    levels = 2**bits
    step = 255 / (levels - 1)

    h, w = img.shape

    for y in range(h):
        for x in range(w):
            old_pixel = img[y, x]

            # 量子化
            new_pixel = round(old_pixel / step) * step
            img[y, x] = new_pixel

            # 誤差
            error = old_pixel - new_pixel

            # Floyd–Steinberg 拡散
            if x + 1 < w:
                img[y, x + 1] += error * 7 / 16
            if y + 1 < h:
                if x > 0:
                    img[y + 1, x - 1] += error * 3 / 16
                img[y + 1, x] += error * 5 / 16
                if x + 1 < w:
                    img[y + 1, x + 1] += error * 1 / 16

    # 範囲クリップしてuint8に戻す
    return np.clip(img, 0, 255).astype(np.uint8)
