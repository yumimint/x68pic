#!/usr/bin/env python3
import io
import sys
import time
from pathlib import Path

from PIL import Image, ImageGrab

from x68pic import Dither, MachineType, PicError, decode, encode


def main():
    import argparse

    from x68pic import __version__

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
    parser.add_argument("--x68fs", action="store_true",
                        help="resize image for X68000 full screen")
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

    kw = {}
    for key in "bpp type mode comment dither".split():
        value = getattr(args, key)
        if value:
            kw[key] = value

    try:
        if args.input.suffix.lower() != ".pic":
            if str(args.input) == "-":
                im = ImageGrab.grabclipboard()
                if im is None:
                    raise ValueError("Image not found in clipboard")
                elif isinstance(im, list):
                    im = Image.open(im[0])
                args.input = Path(f"clipbpard_{int(time.time())}")
            else:
               im = Image.open(args.input)
            if args.x68fs:
                im = padding_image(im, (4, 3)).resize((512, 512))
            out = opath(".pic")
            buf = io.BytesIO()
            encode(buf, im, **kw)
            with out.open("wb") as f:
                f.write(buf.getvalue() + b"\x00")
                #  余分な1byte は pic.r のエラー対策
            if args.show:
                im = decode(buf.getvalue()).show()
        else:
            if args.show:
                with args.input.open("rb") as f:
                    im = decode(f)
                im.show()
                return

            out = opath(".png")
            with args.input.open("rb") as f:
                im = decode(f)
            im.save(str(out))

    except (
        PicError,
        ValueError,
        RuntimeError,
        FileExistsError,
        FileNotFoundError,
    ) as e:
        print(f"{type(e).__name__}: {e}")
        sys.exit(1)


def limit_image_size(img, maxlen=512, minlen: int = None):
    if maxlen is not None:
        s = maxlen / max(img.size)
        if s < 1:
            img = img.resize(tuple(map(lambda x: int(x * s), img.size)))

    if minlen is not None:
        s = minlen / min(img.size)
        if s > 1:
            img = img.resize(tuple(map(lambda x: int(x * s), img.size)))
    return img


def padding_image(img, aspect, fill_color=0):
    i = 1 if aspect[0] > aspect[1] else 0
    L, M = img.size[i], aspect[i]
    new_width = aspect[0] * L // M
    new_height = aspect[1] * L // M
    new_size = (new_width, new_height)
    if new_size == img.size:
        return img

    new_img = Image.new(img.mode, new_size, fill_color)
    left = (new_width - img.size[0]) // 2
    top = (new_height - img.size[1]) // 2
    new_img.paste(img, (left, top))

    return new_img


if __name__ == "__main__":
    main()
