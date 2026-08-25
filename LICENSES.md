# ライセンスと出自

## CP/M 2.2 本体 (CCP/BDOS) と DRI ユーティリティ
- 出自: Digital Research, Inc. (1976-1980)。権利はDRDOS, Inc.が承継。
- 許諾: 2022-07-07、DRDOS, Inc. 代表 Bryan Sparks 氏による声明
  （原文は取得される vendor/cpm22/LICENSE.txt =
  [The Unofficial CP/M Web Site](http://www.cpm.z80.de/license.html) より）:
  "Let this paragraph represent a right to use, distribute, modify,
  enhance, and otherwise make available in a nonexclusive manner CP/M and
  its derivatives."
- 取得: `tools/fetch_cpm22.py` がSHA256検証付きでダウンロードします。
  - ソース: [brouhaha/cpm22](https://github.com/brouhaha/cpm22)
    （Eric Smith氏によるクロスアセンブル向け再整形。実CP/M 2.2ディスクと
    バイト一致することが検証されている系譜）
  - バイナリ: cpm.z80.de の cpm22-b.zip（Xerox 1800用配布ディスク）。
    同梱のCPM.SYSは変換検証の参照としてのみ使用。
- 本リポジトリでの改変:
  - `tools/convert_cpm22.py` によるアセンブラ構文の機械変換
    （意味的変更なし。`tests/test_vendor_match.py` が参照バイナリとの
    バイト一致をシリアル6バイトを除いて保証）
  - シリアルナンバーは0埋め
  - 配布イメージでは BDOS ファンクション13 の JMP 先を1箇所BIOS内へ
    差し替え（リセット時の初期選択ドライブをA:固定→カレントドライブに。
    ハードディスク運用でウォームブート毎にフロッピーが回るのを防ぐため。
    カレントドライブがA:のときの挙動はストックと同一）

## 言語/開発ツール群（`tools/fetch_tools.py` がSHA256検証付きでダウンロード）
- **DRI製品** — MAC、RMAC/LINK/LIB/XREF/Z80.LIB、ZSID、Pascal/MT+ 5.6.1、
  PL/I-80 1.4、CBASIC 2.8。いずれも
  [The Unofficial CP/M Web Site](http://www.cpm.z80.de/) 掲載の配布物で、
  上記 2022-07-07 DRDOS, Inc. 許諾（"CP/M and its derivatives"）の
  傘の下にあります。
- **BDS C 1.60** — 作者 Leor Zolman 氏が2002-09-20にパブリックドメイン化
  （[bdsoft.com](https://www.bdsoft.com/resources/bdsc.html) 掲載の声明:
  "I, Leor Zolman, hereby release all rights to BDS C ... into the
  Public Domain"）。
- 各配布アーカイブから必要ファイルのみ抽出します（一覧と入手元URL・
  SHA256は `tools/fetch_tools.py` が単一情報源）。

## コンソールフォント
- [dhepper/font8x8](https://github.com/dhepper/font8x8) —
  Daniel Hepper / Marcel Sondaar / IBM PD VGA font 系譜、パブリックドメイン。
  `tools/gen_font.py` がビット順を変換して使用。

## SASI ブートROM（本リポジトリには含まれません）
- ハードディスク起動には
  [Enhanced SASI driver for MZ-2500 (EH-SASI)](https://github.com/SuperTurboZ/Enhanced-SASI-driver-for-MZ-2500)
  （CC BY-SA 4.0）のROMを実機/エミュレータ側に用意してください。
  本リポジトリのハードディスクイメージは、そのパーティション表形式に
  準拠しています（相互運用のためのデータフォーマット互換）。

## 本移植分（src/ と tools/ のオリジナル部分）
- MIT License（LICENSE を参照）
