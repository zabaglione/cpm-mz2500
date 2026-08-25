# CP/M 2.2 for SHARP MZ-2500

SHARP MZ-2500 で動く CP/M 2.2 です。DRI純正のCP/M 2.2（2022年に権利者が
再配布・改変を許諾）を移植したもので、ビルド済みディスクイメージを
そのまま使えます。

- 58Kシステム（TPA 52.25KB）、80×25テキスト、ADM-3A互換の画面制御
- **A:/B:** フロッピー（2DD 640KB）
- **C:/D:** SASIハードディスク 8MB×2（MZ-1E30系インタフェース）
- **E:** EMM RAMディスク 620KB（MZ-1R37）＋ 高速ウォームブート
  （^Cやプログラム終了時にディスクを読み直しません。リセットしても
  E: のファイルは消えません）
- **ハードディスクからの起動に対応**（EH-SASI環境。フロッピー不要で
  電源ON→`C>`）
- PIP / STAT / ED / ASM / DDT / SUBMIT / DUMP / LOAD / XSUB を同梱

## ダウンロード

[Releases](../../releases) から:

| ファイル | 内容 |
|---|---|
| `cpm_boot.d88` | 起動フロッピー（ユーティリティ入り） |
| `cpm_data.d88` | フォーマット済みの空フロッピー（B:用） |
| `cpm.hdd` | ハードディスクイメージ（起動可能・ユーティリティ入り） |

## 使い方

### エミュレータで

実IPL対応のMZ-2500エミュレータで `cpm_boot.d88` をFD1に入れて起動して
ください。IPLPRO形式なので、実機ROMを使わないエミュレータでも起動できる
場合があります。

ハードディスク（`cpm.hdd`、256バイト/ブロックのSASI生イメージ）は
SASI対応エミュレータでHD1としてマウントします。HDDから起動するには
EH-SASI ROM（後述）が必要です。

### 実機で — フロッピー

2DD 80シリンダ×2面×16セクタ×256バイトで書き込みます。Greaseweazleの例:

```
gw convert --format=luxor.640 cpm_boot.d88 cpm_boot.img
gw write --drive=B --format=luxor.640 --pre-erase cpm_boot.img
```

### 実機で — ハードディスク（SASI）

MZ-1E30互換インタフェース＋SASI対応のSDカードエミュレータ
（BlueSCSI/ArdSCSino系）＋ [EH-SASI ROM](https://github.com/SuperTurboZ/Enhanced-SASI-driver-for-MZ-2500)
の環境で動作を確認しています。

SDカード上のイメージファイル（例: `HD00_256.HDF` = SASI ID0/LUN0/
256バイトブロック）を `cpm.hdd` の内容に差し替えれば、電源ONだけで
CP/Mが `C>` で立ち上がります。

起動時の操作（EH-SASI環境）:
- そのまま待つ → ハードディスクから自動起動
- **SPACE** → 起動メニュー（F1-F4=HD1-4、1-4=FD1-4）
- **SHIFTを押しながら起動** → HD-BIOSを使わずフロッピー起動

### システムの更新（PUTSYS）

新しい起動フロッピーをA:に入れて

```
A>PUTSYS
```

を実行すると、フロッピーのシステムがハードディスクの起動領域へ複写
されます（C:のファイルには触れません）。実行後にIPLボタンで再起動して
ください。SDカードを抜く必要はありません。

## キー入力のメモ

- 英字は小文字入力でかまいません（CP/Mが大文字化します）
- `=` は SHIFT+`-`、`*` は SHIFT+`:`（JIS配列どおり）
- カーソルキーは ^H ^J ^K ^L、HOME/CLRは ^^ / ^Z を入力します
- フロッピーのモータは約8秒間操作がないと自動停止し、次のアクセスで
  再回転します（約1秒待ってから読み書きします）

## 既知の制約

- カナ入力・ファンクションキーは未対応（ASCIIのみ）
- SUBMITが作る `$$$.SUB` はCP/Mの仕様どおりA:に書かれるため、
  フロッピーを入れていない構成ではSUBMIT/XSUBは実質使えません
- プリンタ出力は未接続（LISTは読み捨て）

## 自分でビルドする

macOS/Linux、Python 3 と z80asm（Bas Wijnen版 1.8, `brew install z80asm`）
が必要です。

```
python3 tools/fetch_cpm22.py   # CP/M本体・ユーティリティ・フォントを取得
make                           # build/ に cpm_boot.d88 / cpm_data.d88 / cpm.hdd
make test                      # 単体テスト（変換結果の原本一致検証を含む）
```

## ライセンス

- CP/M 2.2本体とDRIユーティリティ: DRDOS, Inc.（Bryan Sparks氏）の
  2022-07-07許諾により自由に使用・配布・改変できます
- 本移植のBIOS・ツール類: MIT License
- フォント: パブリックドメイン（font8x8）

詳細と出自は [LICENSES.md](LICENSES.md) を参照してください。

## 謝辞

- [The Unofficial CP/M Web Site](http://www.cpm.z80.de/) — CP/M本体の配布とライセンスの窓口
- [brouhaha/cpm22](https://github.com/brouhaha/cpm22) — クロスアセンブル可能なCP/M 2.2ソース
- [Enhanced SASI driver for MZ-2500 (EH-SASI)](https://github.com/SuperTurboZ/Enhanced-SASI-driver-for-MZ-2500) — ハードディスク起動を支えるSASI BIOS ROM
- [dhepper/font8x8](https://github.com/dhepper/font8x8) — コンソールフォント
