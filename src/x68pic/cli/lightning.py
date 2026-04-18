import argparse
import time
from pathlib import Path

import cv2
import numpy as np

import x68pic.impl
from x68pic.impl import _decode_length
from x68pic.tools import decode_color


class Escape(Exception):
    pass


class WindowClosed(Escape):
    pass


def pause(duration: float | None):
    if duration is None:
        def expired(): return False
    else:
        expiry = time.time() + duration
        def expired(): return time.time() >= expiry

    while not expired():
        key = cv2.waitKey(10)
        if key == 27:
            raise Escape
        if key > 0:
            break


class decode_with_show:
    def __init__(self, step: float):
        self.step = step
        self.visible = True

    def __call__(self, *args, **kwargs):
        if "aux_out" in kwargs:
            self.aux = kwargs.get("aux_out")
        else:
            self.aux = {}
            kwargs.update(dict(aux_out=self.aux))
        backup = x68pic.impl._decode_pixel
        setattr(x68pic.impl, "_decode_pixel", self.decode_pixel)
        try:
            self.skip = False
            return x68pic.decode(*args, **kwargs)
        finally:
            setattr(x68pic.impl, "_decode_pixel", backup)
            del self.aux

    def decode_pixel(self, pixel, read_bit, read_color):
        drawstep = int(pixel.shape[1] * self.step)
        clut = self.make_clut()
        sentinel = drawstep

        flag = np.zeros(pixel.shape, dtype=bool)
        iend = pixel.size

        i = -1
        c = 0

        while i < iend:
            if i >= sentinel:
                self.show(pixel, clut)
                while sentinel < i:
                    sentinel += drawstep

            L = _decode_length(read_bit) - 1
            n = min(iend - (i + 1), L)
            while n:
                n -= 1
                i += 1
                if flag.flat[i]:
                    c = pixel.flat[i]
                    continue
                pixel.flat[i] = c
            i += 1

            if i >= iend:
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

        self.show(pixel, clut, finish=True)

    def make_clut(self) -> np.ndarray | None:
        hd = self.aux["header"]
        if hd.bpp > 16:
            assert hd.bpp == 24
            return None
        format = x68pic.impl._FORMATS[hd.type][hd.bpp]
        if format == "index":
            pal = self.aux["pal"]
            format = self.aux["pal_format"]
        else:
            pal = np.array(range(1 << hd.bpp), dtype=np.uint16)
        return decode_color(pal, format, order="bgr")[0]

    def show(self, pix: np.ndarray, clut: np.ndarray | None, finish=False):
        if not finish and self.skip:
            return

        if clut is None:
            assert pix.dtype == np.uint32
            b, r, g, a = np.moveaxis(
                pix.view(dtype=np.uint8).reshape(pix.shape + (4,)), -1, 0)
            im = np.dstack([b, g, r])
        else:
            im = clut[pix]

        winname = __name__
        cv2.imshow(winname, im)
        key = cv2.waitKey(1)
        if key == 27:
            raise Escape
        if key > 0:
            self.skip = True
        visible = cv2.getWindowProperty(winname, cv2.WND_PROP_VISIBLE) > 0
        if not visible:
            raise WindowClosed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, nargs="*")
    parser.add_argument("--step", type=float, default=1,
                        help="specify lines per frame (>= 0.1)")
    parser.add_argument(
        "--pause",
        metavar="SEC", type=float, nargs="?", default=0,
        help="After the image is displayed, wait for key input for SEC seconds.")
    args = parser.parse_args()

    if args.step and args.step < 0.1:
        raise ValueError(f"step must be >= 0.1, {args.step} given")

    def view(pic: Path):
        decode = decode_with_show(args.step)
        try:
            with pic.open("rb") as f:
                decode(f)
            pause(args.pause)
        except Escape as e:
            raise e
        except Exception as e:
            print(f"{type(e).__name__}: {e}")

    try:
        for path in args.path:
            if path.is_dir():
                for pic in path.rglob("*.pic"):
                    view(pic)
            elif path.suffix.lower() == ".pic":
                view(path)
    except Escape:
        return
    finally:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
