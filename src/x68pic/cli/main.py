#!/usr/bin/env python3
import argparse
import io
import re
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image, ImageGrab

from x68pic import Dither, MachineType, PicError, decode, encode, __version__


parser = argparse.ArgumentParser()
parser.add_argument(
    "--version", action="version", version=f"%(prog)s {__version__}"
)
parser.add_argument("input", type=Path,
                    help="if - specified, grab image from clipboard.")
parser.add_argument("output", type=Path, nargs="?")

parser.add_argument("-b", "--bpp", type=int, help="bits par pixel")
parser.add_argument(
    "-t",
    "--type",
    type=lambda s: MachineType(int(s)),
    help="machine type ([0]:x68 1:88va 2:towns 3:mac 15:gp)",
)
parser.add_argument("-m", "--mode", type=int, help="specify mode")
parser.add_argument("-c", "--comment", type=str, help="comment")
parser.add_argument("--reform", type=str, metavar="ORDER",
                    help="specify image reform instructions")
parser.add_argument("--dither",
                    metavar=("N"),
                    default=Dither.Bayer,
                    type=lambda s: Dither(int(s)),
                    help="Specify dither method (0:NONE, [1]:Bayer, 2:FloydSteinberg)",
                    )
parser.add_argument("--show", action="store_true")
parser.add_argument(
    "--force",
    action="store_true",
    help="Specifying this will force the existing file to be overwritten.",
)

args = parser.parse_args()
# print(args)


def raise_for_exists(path: Path):
    if not args.force and path.exists():
        raise FileExistsError(str(path))


def opath(suffix: str):
    output = args.output or Path(args.input.name).with_suffix(suffix)
    raise_for_exists(output)
    return output


def main_encode():
    if str(args.input) == "-":
        im = ImageGrab.grabclipboard()
        if im is None:
            raise ValueError("Image not found in clipboard")
        elif isinstance(im, list):
            im = Image.open(im[0])
        args.input = Path(f"clipbpard_{int(time.time())}")
    else:
        im = Image.open(args.input)

    out = opath(".pic")

    if args.reform:
        im = reform(im, args.reform)

    buf = io.BytesIO()
    kw = {}
    for key in "bpp type mode comment dither".split():
        value = getattr(args, key)
        if value:
            kw[key] = value
    encode(buf, im, **kw)

    with out.open("wb") as f:
        #  余分なbyte は pic.r のエラー対策
        f.write(buf.getvalue() + b"\x00\x00")

    if args.show:
        im = decode(buf.getvalue()).show()


def main_decode():
    if args.show:
        with args.input.open("rb") as f:
            im = decode(f)
        im.show()
        return

    out = opath(".png")
    with args.input.open("rb") as f:
        im = decode(f)
    im.save(str(out))


def reform_padding(img: Image.Image, match: re.Match) -> Image.Image:
    w, h, fill = match.groups()
    return padding_image(img, (int(w), int(h)), fill)


def reform_resize(img: Image.Image, match: re.Match) -> Image.Image:
    w, h = match.groups()
    return img.resize((int(w), int(h)))


def reform_limit(img: Image.Image, match: re.Match) -> Image.Image:
    args = match.groups()
    return limit_image_size(img, int(args[0]))


def reform(img, order: str):
    functions = [
        (re.compile(r"^L(\d+)$", re.IGNORECASE), reform_limit),
        (re.compile(r"^(\d+)x(\d+)$", re.IGNORECASE), reform_resize),
        (re.compile(r"^(\d+):(\d+)(#[\da-f]+)?$"), reform_padding),
    ]
    for directive in order.split(","):
        for rex, func in functions:
            match = rex.match(directive)
            if match:
                img = func(img, match)
                break
        else:
            raise ValueError(f"'{directive}' is invalid directive")
    return img


def limit_image_size(img: Image.Image, maxlen=512, minlen: Optional[int] = None) -> Image.Image:
    if maxlen is not None:
        s = maxlen / max(img.size)
        if s < 1:
            size = list(map(lambda x: int(x * s), img.size))
            img = img.resize(size, Image.Resampling.LANCZOS)

    if minlen is not None:
        s = minlen / min(img.size)
        if s > 1:
            size = list(map(lambda x: int(x * s), img.size))
            img = img.resize(size)
    return img


def padding_image(img: Image.Image, aspect, fill_color) -> Image.Image:
    # aspect は (横, 縦) の比率を表すタプル
    # 例: (1,1) → 正方形、(16,9) → 横長

    # どちらの辺を基準にリサイズするか決める
    # aspect[0] != aspect[1] の場合は単純に大きい方を基準にする
    if aspect[0] != aspect[1]:
        i = 1 if aspect[0] > aspect[1] else 0
    else:
        # 正方形の場合は画像の縦横どちらが長いかで基準を決める
        i = 1 if img.size[0] < img.size[1] else 0

    # L は基準とする画像の長さ（幅 or 高さ）
    # M は基準とするアスペクト比の値
    L, M = img.size[i], aspect[i]

    # 新しい画像サイズをアスペクト比に合わせて計算
    # L / M を基準にして、aspect の比率に合わせて幅と高さを決める
    new_width = aspect[0] * L // M
    new_height = aspect[1] * L // M
    new_size = (new_width, new_height)

    # すでに同じサイズなら何もせず返す
    if new_size == img.size:
        return img

    # 新しいキャンバスを作成（背景色 fill_color）
    new_img = Image.new(img.mode, new_size, fill_color)

    # 元画像を中央に配置するための余白を計算
    left = (new_width - img.size[0]) // 2
    top = (new_height - img.size[1]) // 2

    # 新しいキャンバスに元画像を貼り付ける
    new_img.paste(img, (left, top))

    return new_img


def main():
    try:
        if args.input.suffix.lower() != ".pic":
            main_encode()
        else:
            main_decode()
    except (
        PicError,
        ValueError,
        RuntimeError,
        FileExistsError,
        FileNotFoundError,
    ) as e:
        print(f"{type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
