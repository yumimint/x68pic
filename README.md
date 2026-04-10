# x68pic

x68pic は、シャープのレトロパソコン X68000 シリーズの標準画像フォーマット（.PIC）を Python で扱うためのライブラリです。

## 特徴

- X68k 全モード対応: 16 / 256 / 32768 (15bit) / 65536 (16bit) 色のすべてをサポート。

- 高品質なエンコード: 24bit カラーなどの高色階調画像を 16/15/12/8bit へ変換する際、ディザリング（Dithering） を適用して階調を維持したまま変換可能です。

- エコシステム連携: numpy 配列を介して Pillow 等の主要ライブラリとシームレスに連携します。

## インストール

```bash
git clone https://github.com/yumimint/x68pic.git
cd x68pic
pip install .
```

または

```bash
pip install git+https://github.com/yumimint/x68pic.git
```

※ 依存ライブラリ: numpy, pillow

## 使い方

### PIC ファイルを読み込む (Decode)

```Python
import x68pic

with open("input.pic", "rb") as f:
    img = x68pic.decode(f)
img.save("output.png")
```

### PICファイルを生成する (Encode)

```Python
import x68pic
from PIL import Image

img = Image.open("photo.jpg")

with open("output.pic", "wb") as f:
    # 15bit(32768色)モードでディザリングを適用してエンコード
    x68pic.encode(f, img, 15, dither=True)
```

### OpenCVを使った簡易ビュアー

```Python
from pathlib import Path

import cv2

import x68pic


ESCAPE = 27

def show(im):
    winname = "picview"
    cv2.imshow(winname, im)
    while True:
        if cv2.getWindowProperty(winname, cv2.WND_PROP_VISIBLE) < 1:
            return ESCAPE
        k = cv2.waitKey(-1)
        if k > 0:
            break
    return k

for path in Path(".").rglob("*.pic"):
    try:
        with path.open("rb") as f:
            im = x68pic.decode(f, "bgr")
        k = show(im)
        if k == ESCAPE:
            break
    except x68pic.PicError as e:
        print(f"{type(e).__name__}: {e}: {path}")

cv2.destroyAllWindows()
```

## ライセンス

MIT License

## 作者

yumimint <i.yumimint@gmail.com>
