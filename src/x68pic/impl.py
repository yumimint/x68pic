import enum
import io
from collections import namedtuple
from typing import Any, BinaryIO, Callable, Optional, Sequence, Union

import numpy as np
from PIL import Image

from x68pic.tools import BitStream, Dither, decode_color, encode_color


class PicError(Exception):
    pass


class PicFormatError(PicError):
    pass


class MachineType(enum.Enum):
    X68 = 0
    PC88VA = 1
    FMTOWNS = 2
    MAC = 3
    GP = 15  # general purpose


IMG = Union[Image.Image, np.ndarray]
PICH = namedtuple(
    "PICH", "comment mode type bpp width height sx sy aw ah pal_bits")


def header(buf: Union[BinaryIO, bytes]) -> PICH:
    return _read_header(BitStream(buf))


def decode(
    buf: Union[BinaryIO, bytes],
    type: Optional[str] = "pil",
    aux_out: Optional[dict[str, Any]] = None,
) -> Optional[IMG]:
    """
    PIC画像ファイルをデコードします

    :param buf: PICファイル
    :param type: 出力形式

        - "pil" Pillow (デフォルト)
        - "bgr" NumPy (OpenCV)
        - "rgb" NumPy
        - 任意の"rgb" NumPy

    :params aux_out: 補助出力

    :returns: デコードされた画像 (NumPy or Pillow Image)
    """
    if type is not None:
        if len(type) == 3 and set(type) == set("rgb"):
            order = type
        elif type == "pil":
            order = "rgb"
        else:
            raise ValueError(f"{type} is not a valid type")

    aux_out = aux_out if aux_out is not None else {}

    bs = BitStream(buf)
    hd = _read_header(bs)
    aux_out["header"] = hd
    hd_size = bs.size

    dtype = np.uint8 if hd.bpp <= 8 else (
        np.uint16 if hd.bpp <= 16 else np.uint32)
    pixel = np.zeros((hd.height, hd.width), dtype=dtype)

    format = _FORMATS[hd.type][hd.bpp]

    if format == "index":
        # パレットを読み出す
        m = hd.pal_bits or 0
        n = (m * 3) or 16
        pal_format = "g5r5b5i1" if m == 0 else f"g{m}r{m}b{m}"
        pal = np.array([bs.read(n)
                       for _ in range(1 << hd.bpp)], dtype=np.uint32)

        aux_out["pal"] = pal
        aux_out["pal_format"] = pal_format

    # ピクセルをデコード
    _decode_pixel(pixel, bs.read, _ColorIO("r", hd.bpp, bs.read))
    aux_out["read_bits"] = (hd_size, bs.size - hd_size)

    # PC-88VAの「一見64K色、実は256色」モード
    if hd.mode & 2 and hd.type == MachineType.PC88VA and hd.bpp == 16:
        pixel = pixel.astype("<u2").view(dtype=np.uint8)
        pixel = pixel.reshape((hd.height * 2, hd.width))
        format = _FORMATS[hd.type][8]
        # modeみて判断すればいいので小細工はコメントアウト
        # meta = hd._asdict()
        # meta["bpp"] = 8
        # meta["mode"] &= -2
        # aux_out["header"] = PICH(*meta)

    aux_out["pixel"] = pixel

    if type is None:
        return None

    im: IMG
    if format == "index":
        if type == "pil":
            im = Image.fromarray(pixel, mode="P")
            clut = decode_color(pal, pal_format, order="rgb")
            im.putpalette(clut[0].flat)
        else:
            clut = decode_color(pal, pal_format, order=order)
            im = clut[0][pixel]  # ファンシーインデックス
    else:
        im = decode_color(pixel, format, order=order)
        if type == "pil":
            im = Image.fromarray(im)

    return im


def encode(
    buf: BinaryIO,
    im: IMG,
    order: Optional[str] = None,
    pal: Optional[Sequence[int]] = None,
    *,
    bpp: Optional[int] = None,
    comment: Optional[Union[str, bytes]] = None,
    type: Optional[Union[MachineType, int]] = None,
    mode: Optional[int] = None,
    dither: Optional[Dither] = None,
    pal_bits: int = 0,
):
    """画像をPIC形式でエンコードします

    :param buf: 出力ファイル
    :param im: 入力画像 (NumPy or Pillow)
    :param order: 入力画像(NumPy)のRGB順
    :keyword pal: パレット (Pillow の getpalette と同形式)
    :keyword bpp: 出力ビット数

        4, 8, 12, 15, 16, 24 の何れかを設定できます。
        ダイレクトカラーのデフォルトは 15
        インデックスカラーなら 4 か 8 を内部で判定

    :keyword dither: ディザリングを適用するか
    :keyword type: 機種タイプ

        未指定ならbppから決定されます。
        X68000が優先されるためPC-88VAの16bitを使いたい等のケースで指定します。

        15/16bit正方(1:1)を扱うケースではアスペクト情報を有する `MachineType.GP` を指定するとよいでしょう。

    :param mode: モード指定
    :param pal: パレットデータ
        [r0, g0, b0, r1, g1, b1, ...]

    :param pal_bits: パレットビット長 n

        色コードとの関係は次の通り
        ````
        n == 0 : "g5r5b5i1"
        n > 0 : f"g{n}r{n}b{n}"
        ````

    """
    # 画像の正規化
    im, pal, order = _regurate_image(im, pal, order)
    assert isinstance(im, np.ndarray)
    # im: NumPy配列であることが保証される

    # bpp選定
    if bpp is None:
        if pal is None:
            bpp = 15
        else:
            assert isinstance(im, np.ndarray)
            n = int(im.max()).bit_length()
            if n > 8:
                raise ValueError(f"{n}bit index is not a valid depth")
            bpp = 4 if n <= 4 else 8

    # 機種type選定
    if type is None:
        for mtype, md in _FORMATS.items():
            if bpp in md.keys():
                type = mtype
                break
        else:
            raise ValueError(f"{bpp} is not a valid bpp")
    else:
        if isinstance(type, int):
            type = MachineType(type)
        if bpp not in _FORMATS[type]:
            raise ValueError(f"{bpp} is not a valid bpp for {type.name}")
        if type == MachineType.GP:
            # apicg.r はpal_bits==0 をx68k ネイティブとして扱うが、
            # OPTPiXでは壊れたファイル認定されてしまう。
            # それはそうと、OPTPiXってGORRYさん作だったのですね。
            # どうりでPICもサポートされていたわけだ。:)
            # バージョン情報ダイアログにスタッフロールが隠ているのを今頃(2026)気づきました。
            pal_bits = 5

    # ピクセルとパレットをPIC用コードへ変換
    m = pal_bits
    pal_format = "g5r5b5i1" if m == 0 else f"g{m}r{m}b{m}"

    pixel, pal = _to_pic_code(
        im, order, pal, bpp, _FORMATS[type][bpp], dither, pal_format
    )

    height, width = pixel.shape

    # PC-88VAの「一見64K色、実は256色」モード
    if mode is not None and mode & 2 and type == MachineType.PC88VA and bpp == 8:
        assert pixel.dtype == np.uint8
        if height & 1:  # 縦ライン数を偶数に保障
            pixel = np.vstack([pixel, np.zeros((1, width), dtype=np.uint8)])
        # あるいは奇数は不可とする
        # if height & 1:
        #     raise ValueError("height must be even")
        height //= 2
        pixel = pixel.view(dtype="<u2").reshape((height, width))
        bpp = 16

    # -------- エンコード開始 --------

    bs = BitStream(buf)

    # ヘッダを書き込む
    header_bytes = new_header(
        bpp=bpp,
        width=width,
        height=height,
        type=type,
        mode=mode or 0,
        comment=comment,
        pal_bits=pal_bits,
    )
    bs.write_bytes(header_bytes)

    # パレットを書き込む
    if pal is not None:
        assert len(pal) == 1 << bpp
        n = (pal_bits * 3) or 16
        for code in pal:
            bs.write(n, code)

    # ピクセルをエンコードして書き込む
    _encode_pixel(pixel, bs.write, _ColorIO("w", bpp, bs.write))

    bs.flush()


def _regurate_image(im, pal, order):
    if isinstance(im, np.ndarray):
        if im.dtype != np.uint8:
            raise ValueError("image must be uint8")
    elif isinstance(im, Image.Image):
        if im.mode[0] == "P":
            pal = im.getpalette()
        im = np.asarray(im)
        order = order or "rgb"
    else:
        raise ValueError("image must be Pillow or NumPy image")

    if im.ndim == 2 and pal is None:
        raise ValueError("Indexed color images require a palette")
    if im.ndim == 3 and pal is not None:
        raise ValueError("Palette is not needed")

    return im, pal, order


def split_pic(buf: Union[BinaryIO, bytes]) -> tuple[bytes, bytes]:
    """
    PICファイルをヘッダと本体に分割します

    :param buf: PICファイル

    :return: ヘッダと本体の bytes のタプル

    Examples
    --------
        ```
        with open("input.pic", "rb") as f:
            head, body = x68pic.split_pic(f)
        meta = x68pic.header(head)._asdict()
        meta["comment"] = "/MM/XSS:恵美ちゃんカワイイよエミちゃん(*´ω｀*)"
        with open("output.pic", "wb") as f:
            f.write(x68pic.new_header(**meta) + body)
        ```
    """

    # デコードしてサイズを特定
    info: dict[str, Any] = {}
    decode(buf, None, aux_out=info)

    if isinstance(buf, bytes):
        buf = io.BytesIO(buf)
    head, body = info["read_bits"]

    buf.seek(0)
    return buf.read(head // 8), buf.read((body + 7) // 8)


#############################################################################

# 機種毎のbppとピクセルフォーマットの関係を定義する
_FORMATS: dict[MachineType, dict] = {
    # bppから機種を選定するときの優先順
    MachineType.X68: {
        4: "index",
        8: "index",
        15: "g5r5b5",
        16: "g5r5b5i1",
    },
    MachineType.GP: {
        4: "index",
        8: "index",
        12: "g4r4b4",
        15: "g5r5b5",
        16: "g5r5b5i1",
        24: "g8r8b8",
    },
    MachineType.PC88VA: {
        8: "g3r3b2",
        12: "g4r4b4",
        16: "g6r5b5",
    },
    MachineType.FMTOWNS: {
        15: "g5r5b5",
    },
    MachineType.MAC: {
        15: "r5g5b5",
    },
}


def _ColorIO(mode: str, bpp: int, bit_io: Callable) -> Callable:
    """色I/O関数を取得します

    :param mode: モード "r" or "w"
    :param bpp: 色のビット長
    :param bit_io: ビット読み書き関数

    :return:  色I/O関数
    """
    if bpp >= 12:
        cc = _ColorCache()
        if mode == "r":

            def read_with_cache() -> int:
                if bit_io(1):
                    c = cc.get(bit_io(7))
                else:
                    c = cc.put(bit_io(bpp))
                return c

            return read_with_cache
        else:

            def write_with_cache(color):
                color = int(color)
                i = cc.find(color)
                if i >= 0:
                    cc.get(i)
                    bit_io(1, 1)
                    bit_io(7, i)
                else:
                    cc.put(color)
                    bit_io(1, 0)
                    bit_io(bpp, color)

            return write_with_cache
    else:
        if mode == "r":

            def read_raw() -> int:
                return bit_io(bpp)

            return read_raw
        else:

            def write_raw(color):
                color = int(color)
                bit_io(bpp, color)

            return write_raw


class _ColorCache:
    def __init__(self):
        self.table = [self.node() for i in range(128)]
        self.color_p = self.table[0]  # 最新色を指す
        for i, p in enumerate(self.table):
            p.color = 0
            p.prev = self.table[(i + 1) & 127]
            p.next = self.table[i - 1]

    def __del__(self):
        # 循環参照を解消
        for p in self.table:
            p.next = p.prev = None
        self.color_p = None
        del self.table

    def get(self, idx: int) -> int:
        """キャッシュから色を取り出しその色が最新になるように更新する"""
        p = self.table[idx]
        if p != self.color_p:
            self.color_p = p.cut().insert(self.color_p)
        return p.color

    def put(self, color: int) -> int:
        """新しい色をキャッシュに登録"""
        self.color_p = self.color_p.prev
        self.color_p.color = color
        return color

    def find(self, color: int) -> int:
        for i, p in enumerate(self.table):
            if p.color == color:
                return i
        return -1

    class node:
        def __init__(self):
            self.color = 0
            # self.next = self
            # self.prev = self

        def cut(self):
            self.next.prev = self.prev
            self.prev.next = self.next
            # self.next = self
            # self.prev = self
            return self

        def insert(self, place):
            place.prev.next = self
            self.prev = place.prev
            place.prev = self
            self.next = place
            return self


def _encode_length(write_bit: Callable, x: int):
    bits = (x + 1).bit_length() - 1  # 2進数での桁数計算
    lead = (1 << bits) - 1
    write_bit(bits, lead ^ 1)
    write_bit(bits, x - lead)


def _decode_length(read_bit: Callable) -> int:
    bits = 0
    while True:
        bits += 1
        if read_bit(1) == 0:
            break
    x = read_bit(bits)
    x += (1 << bits) - 1
    return x


def _read_header(bs: BitStream) -> PICH:
    """BitStreamからPICのヘッダを読み出します

    :param bs: BitStream
    :return: PICH (namedtuple)
    ```
    """
    magic = bs.read_bytes(3)
    if magic != b"PIC":
        raise PicFormatError("Magic not match")

    comment = bs.read_until(b"\x1a")
    dummy = bs.read_until(b"\x00")  # 真のコメントの終わり  # noqa: F841

    reserve = bs.read(8)  # noqa: F841
    mode = bs.read(4)
    type: int | MachineType = bs.read(4)
    try:
        type = MachineType(type)
    except ValueError as e:
        raise PicFormatError(str(e))
    bpp = bs.read(16)
    width = bs.read(16)
    height = bs.read(16)

    if bpp not in _FORMATS[type]:
        raise PicFormatError(f"{bpp} is unknown bpp on {type.name}")

    sx, sy = None, None
    aw, ah = None, None
    pal_bits = None
    if type == MachineType.GP:
        sx = bs.read(16)  # セーブ座標 Ｘ（－１指定でなし）
        sy = bs.read(16)  # セーブ座標 Ｙ（－１指定でなし）
        aw = bs.read(8)  # 本当の比率  横
        ah = bs.read(8)  # 本当の比率  縦
        if bpp in [4, 8]:
            pal_bits = bs.read(8)  # パレットのビット長 ( 256/16色の時のみ存在）

    comment_ = comment.decode(encoding="ShiftJIS", errors="surrogateescape")

    return PICH(comment_, mode, type, bpp, width, height, sx, sy, aw, ah, pal_bits)


def new_header(
    bpp: int,
    width: int,
    height: int,
    *,
    type: MachineType = MachineType.X68,
    mode: int = 0,
    comment: Optional[Union[str, bytes]] = None,
    sx=None,
    sy=None,
    aw=None,
    ah=None,
    pal_bits=None,
) -> bytes:
    """
    PICファイルのヘッダブロックを作ります

    :rtype: bytes
    """
    buf = io.BytesIO()
    bs = BitStream(buf)

    hd = b"PIC"
    if comment:
        if isinstance(comment, str):
            hd += comment.encode(encoding="ShiftJIS")
        else:
            hd += comment
    hd += b"\x1a"
    hd += b"\x00"  # 真のコメントの終わり
    hd += b"\x00"  # 予約
    bs.write_bytes(hd)

    bs.write(4, mode)  # # bit 4..7 機種毎のモード
    bs.write(4, type.value)  # # bit 0..3 機種タイプ
    bs.write(16, bpp)
    bs.write(16, width)
    bs.write(16, height)

    if type == MachineType.GP:
        bs.write(16, sx or 0xFFFF)
        bs.write(16, sy or 0xFFFF)
        bs.write(8, aw or 1)
        bs.write(8, ah or 1)
        if bpp in [4, 8]:
            bs.write(8, pal_bits or 0)

    bs.flush()

    return buf.getvalue()


def _decode_pixel(pixel: np.ndarray, read_bit: Callable, read_color: Callable):
    """PIC圧縮データをピクセル配列にデコードします

    :param pixel: ピクセル配列
    :param read_bit: ビット読み出し関数
    :param read_color: 色読み出し関数
    """
    flag = np.zeros(pixel.shape, dtype=bool)
    iend = pixel.size

    i = -1  # 開始座標(-1, 0)
    c = 0  # 色のスタートは0
    # 最初のピクセル色が0でない場合、空の区画(L=0)が現れる

    while i < iend:
        L = _decode_length(read_bit) - 1  # 区画のピクセル数
        n = min(iend - (i + 1), L)
        while n:  # 区画描画ループ
            n -= 1
            i += 1
            if flag.flat[i]:
                # 連鎖点上を通過した時は、現在の色を変更
                c = pixel.flat[i]
                continue
            pixel.flat[i] = c

        i += 1  # 次の区画へ進む
        if i >= iend:
            # 最終ピクセルまで描ききった
            break

        c = read_color()
        pixel.flat[i] = c

        if read_bit(1):
            y, x = np.unravel_index(i, pixel.shape)

            while True:
                lr = read_bit(2)
                if lr == 0:
                    if not read_bit(1):
                        break
                    else:
                        d = 2 if read_bit(1) else -2
                elif lr == 1:
                    d = -1
                elif lr == 2:
                    d = 0
                elif lr == 3:
                    d = 1
                y, x = y + 1, x + d
                try:
                    pixel[y, x] = c
                    flag[y, x] = True
                except IndexError:
                    pass
                    # 破損データ対策


def _encode_pixel(pixel: np.ndarray, write_bit: Callable, write_color: Callable):
    """ピクセルデータをPIC形式にエンコードします

    :param pixel: ピクセル配列
    :param write_bit: ビット書き込み関数
    :param write_color: 色書き込み関数
    """
    flg = np.zeros(pixel.shape, dtype=np.bool)

    # 変化点にフラグを立てる
    c = 0
    for i, pc in enumerate(pixel.flat):
        if c != pc:
            c = pc
            flg.flat[i] = True

    last = -1
    imax = pixel.size
    i = 0
    while i < imax:
        if flg.flat[i]:
            # 変化点を見つけたら区間の長さを書き出す
            _encode_length(write_bit, i - last)
            last = i

            # 次の区画へ進む
            write_color(pixel.flat[i])
            _encode_chain(write_bit, pixel, flg, i)
        i += 1

    _encode_length(write_bit, i - last)


def _encode_chain(write_bit: Callable, pixel: np.ndarray, flag: np.ndarray, i: int):
    c = pixel.flat[i]
    starty, startx = np.unravel_index(i, pixel.shape)
    height, width = pixel.shape

    chain = []

    y, x = starty + 1, startx
    while y < height:
        for dx in [0, -1, 1, -2, 2]:
            ix = x + dx
            if 0 <= ix < width and flag[y, ix] and pixel[y, ix] == c:
                chain.append(dx)
                x = ix
                y += 1
                break
        else:
            break

        # 連鎖が512(の倍数)ラインを超えないための制限
        if (y % 512) == 0:
            break

    if not chain:
        write_bit(1, 0)  # 連鎖ナシ
        return

    write_bit(1, 1)  # 連鎖あります

    chaincode = [
        # dxからコードを参照するリスト
        (2, 2),  # 0 中  10
        (2, 3),  # 1 右1 11
        (4, 3),  # 2 右2 00-11
        (4, 2),  # -2 左2 00-10
        (2, 1),  # -1 左1 01
    ]

    y, x = starty, startx
    for dx in chain:
        x += dx
        y += 1
        # assert flg[y, x] and pix[y, x] == c
        flag[y, x] = False
        bits, code = chaincode[dx]
        write_bit(bits, code)
    write_bit(3, 0)  # 00-0 連鎖情報終わり


def _to_pic_code(
    im, order, pal, bpp, format, dither, pal_format
) -> tuple[np.ndarray, list[int] | None]:
    """画像やパレットをPIC用コードへ変換します"""
    if format == "index":
        if pal is None:
            im = np.dstack(
                [
                    im[:, :, order.index("r")],
                    im[:, :, order.index("g")],
                    im[:, :, order.index("b")],
                ]
            )
            im = Image.fromarray(im).convert(
                "P", palette=Image.Palette.ADAPTIVE, colors=1 << bpp
            )
            pixel = np.asarray(im)
            pal = im.getpalette()
        else:
            if im.max() >= 1 << bpp:
                # PからPへconvertすると意図した通りに減色されなかったので一度RGBにする
                pal_im = np.array(pal, dtype=np.uint8).reshape((-1, 3))
                im = Image.fromarray(pal_im[im]).convert(
                    "P", palette=Image.Palette.ADAPTIVE, colors=1 << bpp
                )
                pixel = np.asarray(im)
                pal = im.getpalette()
            else:
                pixel = im

        pal_code = _encode_palette(1 << bpp, pal_format, pal)
        return pixel, pal_code

    # ダイレクトカラー

    if pal:
        pal_im = np.array(pal, dtype=np.uint8).reshape((-1, 3))
        clut = encode_color(pal_im, format, order="rgb")
        pixel = clut[im]
    else:
        pixel = encode_color(im, format, order=order or "bgr", dither=dither)

    return pixel, None


# def _reindex(im: Image.Image) -> Image.Image:
#     """パレットから未使用色を取り除いてインデックスを振り直す
#     """
#     assert im.mode == "P"

#     pixel = np.asarray(im)
#     assert pixel.dtype == np.uint8
#     colors = set(map(int, pixel.flat))
#     clut = np.array(im.getpalette()).reshape((-1, 3))

#     reidx = []
#     choosed = []
#     j = 0
#     for i in range(pixel.max() + 1):
#         reidx.append(j)
#         if i in colors:
#             choosed.append(i)
#             j = j + 1

#     new_clut = clut[np.array(choosed)]
#     new_pixel = np.array(reidx, dtype=np.uint8)[pixel]

#     im = Image.fromarray(new_pixel, mode="P")
#     im.putpalette(new_clut.flat)

#     return im


def _encode_palette(n: int, pal_format: str, pal: Sequence[int]) -> list:
    """パレットをカラーコードのリストとしてエンコードします

    :param n: パレット長
    :param pal_format: カラーコードフォーマット
    :param pal: パレットデータ

            [r0, g0, b0, r1, g1, b1, ...]

    :rtype: list[int]
    :returns: カラーコードのリスト
    """
    if not isinstance(pal, list):
        pal = list(pal)

    rgb_array = np.array(pal[: n * 3], dtype=np.uint8).reshape((-1, 3))
    code_array = encode_color(rgb_array, pal_format, order="rgb")

    ls = list(map(int, code_array))
    ls.extend([0] * (n - len(ls)))

    return ls
