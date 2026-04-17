# x68pic

x68pic は、シャープのレトロパソコン X68000 シリーズの標準画像フォーマット（.PIC）を Python で扱うためのライブラリです。

## 特徴

- 全機種対応:

    PICの仕様にある全機種(X68000, PC-88VA, FM-TOWNS, MAC, 汎用)をサポートしています。

    ※当モジュールでエンコードしたPICを本家`pic.r`、`apicg.r`、[OPTPiX Snap](https://www.webtech.co.jp/products/old_products.html)にて確認しました。
    X68以外の機種については「 *OPTPiXで読めたのだからたぶん大丈夫* 」 に依拠しております。(^^;)

- 高品質なエンコード:

    24bit カラーなどの高色階調画像を 16/15/12/8bit へ変換する際、
    ディザリング（Dithering） を適用して階調を維持したまま変換可能です。

- エコシステム連携: numpy 配列を介して Pillow 等の主要ライブラリとシームレスに連携します。

## インストール

```sh
git clone https://github.com/yumimint/x68pic.git
cd x68pic
pip install .
```

または

```sh
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

```Python:picview.py
from pathlib import Path

import cv2

import x68pic


ESCAPE = 27

def show(im):
    winname = "picview"
    cv2.imshow(winname, im)
    while True:
        if cv2.getWindowProperty(winname, cv2.WND_PROP_VISIBLE) < 1:
            k = ESCAPE
            break
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

```sh
$ x68pic -h
usage: x68pic [-h] [--version] [-b BPP] [-t TYPE] [-m MODE] [-c COMMENT] [--x68fs] [--dither] [--show] [--force] input [output]
```

- `input`がPICならデコード、そうでなければエンコードします。（拡張子で判定）
- `output`は省略できます。
    その場合、`input`の拡張子を`.pic`あるいは`.png`としたファイル名を用います。以下の例ではカレントディレクトリに`hoge.png`が生成されます。

    ```sh
    x68pic dennouclub/garou/hoge.pic
    ```

- `input`に`-`を指定するとクリップボードを読み込みます。
    ファイル名は`clipboard_#`となります。(#はタイムスタンプ)

#### コマンド使用例

##### png -> pic (エンコード)

```sh
x68pic input.png output.pic
```

##### pic -> png (デコード)

```sh
x68pic input.pic output.png
```

##### PIC画像を表示 (--show)

```sh
x68pic --show input.pic
```

エンコードするときに --show するとエンコード結果を表示します。

##### PC-88VAの256色モード、ディザリング適用してエンコード

```sh
x68pic -t1 -b8 --dither foobar.bmp
```

##### PC-88VAの特殊256色モードでエンコード

一見16bitカラーだが実は8bitカラーという形式です。
`-m2`でモード2を指定します。

```sh
x68pic -t1 -b8 -m2 foobar.bmp
```

##### 正方(1:1)でエンコード

```sh
x68pic -t15 foobar.bmp
```

以下の3タイプは正方(1:1)となります。

- 汎用`-t15`、モード0`-m0`(※)
- FM-TOWNS`-t2`
- MAC`-t3`

※ 未指定はモード0です。`-m1`でX68000のアスペクトになります。

[PIC 拡張ヘッダ](http://retropc.net/x68000/software/graphics/pic/picheader.htm)を使って正方にする方法もあります。ただしOPTPiXは非対応のようです。（OPTPiX Snap 4.03.00-MP）

```sh
x68pic -C /MM/XSS: foobar.bmp
```

##### クリップボードからX68000用フルスクリーン画像を生成する (--x68fs)

入力画像の縦横比を4:3に余白を追加して512x512へリサイズします。
クリップボード入力と組み合わせると便利かもしれません。
エンコード時のみ有効。

```sh
x68pic --x68fs --dither -
```

## 謝辞

開発には以下の資料を参考にさせて頂きました。この場を借りて深く感謝申し上げます。

- [PICフォーマット仕様書](https://www.vector.co.jp/soft/data/art/se003198.html)

    いわずもがな

- [GORRY's Homepage - X68Index](https://gorry.haun.org/x68index.html) apicgソースコード

    機種タイプ15(汎用)におけるパレットのビット長の解釈について参考になりました。

## ライセンス

MIT License

## 作者

yumimint <i.yumimint@gmail.com>
