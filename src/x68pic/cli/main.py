#!/usr/bin/env python3
import io
import sys
from pathlib import Path

from PIL import Image

from x68pic import MachineType, PicError, decode, encode


def main():
    import argparse

    from x68pic import __version__

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path, nargs="?")

    parser.add_argument("-b", "--bpp", type=int, help="bits par pixel")
    parser.add_argument(
        "-t",
        "--type",
        type=lambda s: MachineType(int(s)),
        help="machine type 0:x68 1:88va 2:towns 3:mac 15:gp",
    )
    parser.add_argument("-m", "--mode", type=int, help="specify mode")
    parser.add_argument("-c", "--comment", type=str, help="comment")
    parser.add_argument("--dither", action="store_true")
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
            im = Image.open(args.input)
            out = opath(".pic")
            buf = io.BytesIO()
            encode(buf, im, **kw)
            with out.open("wb") as f:
                f.write(buf.getvalue() + b"\x00")
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


if __name__ == "__main__":
    main()
