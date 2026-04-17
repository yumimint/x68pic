# x68pic

x68pic は、シャープのレトロパソコン X68000 シリーズの標準画像フォーマット（.PIC）を Python で扱うためのライブラリです。

## 特徴

- 全機種対応:

    PICの仕様にある全機種(X68000, PC-88VA, FM-TOWNS, MAC, 汎用)をサポートしています。

    ※XM6、[OPTPiX](https://www.webtech.co.jp/products/old_products.html)にて確認。

- 高品質なエンコード:

    24bit カラーなどの高色階調画像を 16/15/12/8bit へ変換する際、
    ディザリング（Dithering） を適用して階調を維持したまま変換可能です。

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
    cv2.destroyWindow(winname)
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

```

### x68pic コマンド

Pillowがサポートしている各種画像形式とPICを相互に変換できます。
`input`がPICならデコード、そうでなければエンコードします。（拡張子で判定）
`-` を指定するとクリップボードを読み込みます。


```sh
$ x68pic -h
usage: x68pic [-h] [--version] [-b BPP] [-t TYPE] [-m MODE] [-c COMMENT] [--x68fs] [--dither] [--show] [--force] input [output]
```

#### png -> pic

```sh
x68pic input.png output.pic
```

#### pic -> png

```sh
x68pic input.pic output.png
```

#### PIC画像を表示 (--show)

```sh
x68pic --show input.pic
```

エンコードするときに --show するとエンコード結果を表示します。

#### PC-88VAの256色モードをディザリングありでエンコード

```sh
x68pic -t1 -b8 --dither foobar.bmp
```

#### PC-88VAの特殊256色モードでエンコード

16bitカラーとして圧縮されてるが実は8bitカラーという形式です。
`-m2`でモード2を指定します。

```sh
x68pic -t1 -b8 -m2 foobar.bmp
```

#### 1:1正方PICでエンコード

```sh
x68pic -t15 foobar.bmp
```

機種タイプを15(汎用)にすると1:1の正方PICになります。FM-TOWNS`-t2`も正方となります。

## ライセンス

MIT License

## 作者

yumimint <i.yumimint@gmail.com>
