import argparse
import contextlib
from pathlib import Path

import cv2
import numpy as np

import x68pic.impl
from x68pic.impl import _decode_length
from x68pic.tools import decode_color


class lighting_visualizer:
    @classmethod
    @contextlib.contextmanager
    def create(cls, step):
        obj = cls()
        obj.step = step
        try:
            decode_pixel = x68pic.impl._decode_pixel
            setattr(x68pic.impl, "_decode_pixel", obj.decode_pixel)
            yield obj
        finally:
            setattr(x68pic.impl, "_decode_pixel", decode_pixel)
            cv2.destroyAllWindows()

    def decode(self, *args, **kwargs):
        self.aux = {}
        return x68pic.decode(*args, **kwargs, aux_out=self.aux)

    def draw(self, pix: np.ndarray):
        cv2.waitKey(1)
        if self.clut is None:
            assert pix.dtype == np.uint32
            b, r, g, a = np.moveaxis(
                pix.view(dtype=np.uint8).reshape(pix.shape + (4,)), -1, 0)
            im = np.dstack([b, g, r])
        else:
            im = self.clut[pix]
        cv2.imshow(__name__, im)

    def build_clut(self):
        hd = self.aux["header"]
        format = x68pic.impl._FORMATS[hd.type][hd.bpp]
        if format == "index":
            pal = self.aux["pal"]
            pal_format = self.aux["pal_format"]
            self.clut = decode_color(pal, pal_format, order="bgr")[0]
        else:
            if hd.bpp <= 16:
                self.clut = decode_color(
                    np.array(range(1 << hd.bpp), dtype=np.uint16),
                    format, order="bgr")[0]
            else:
                self.clut = None

    def decode_pixel(self, pixel, read_bit, read_color):
        drawstep = int(pixel.shape[1] * self.step)
        self.build_clut()

        flag = np.zeros(pixel.shape, dtype=bool)
        iend = pixel.size
        inext = 0

        i = -1
        c = 0

        while i < iend:
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

            if i >= inext:
                inext += drawstep
                self.draw(pixel)

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
        self.draw(pixel)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path, nargs="*")
    parser.add_argument("--step", type=float, default=1.0,
                        help="specify lines per frame (>= 0.1)")
    args = parser.parse_args()
    if args.step and args.step < 0.1:
        raise ValueError(f"{args.step} must be >= 0.1")

    with lighting_visualizer.create(args.step) as lv:
        for path in args.path:
            if path.is_dir():
                for pic in path.rglob("*.pic"):
                    try:
                        with pic.open("rb") as f:
                            lv.decode(f)
                        # cv2.waitKey(-1)
                    except Exception as e:
                        print(f"{type(e).__name__}:{e}")
            else:
                try:
                    with path.open("rb") as f:
                        lv.decode(f)
                    # cv2.waitKey(-1)
                except Exception as e:
                    print(f"{type(e).__name__}:{e}")


if __name__ == "__main__":
    main()
