# ライセンスと出自

## CP/M Plus（CCP/BDOS）とDRIユーティリティ

- 著作権: Digital Research / DRDOS, Inc.。2022-07-07のBryan Sparks氏による
  CP/Mと派生物の再配布・改変許諾。原文は取得後の`vendor/cpm3/LICENSE.txt`。
- 配布元: [Digital Research CP/M releases](https://www.seasip.info/Cpm/software/dri.html)。
  `cpm3bin_unix.zip`と`cpm3src_unix.zip`を`tools/fetch_cpm3.py`がSHA256照合付きで取得。
- 使用: 非バンク版`bdos3.spr`、`ccp.com`、標準ユーティリティ。
- 本移植で行う処理: SPRのアドレス再配置とSCB設定。DRIの命令列やシリアルを
  任意変更するパッチは使用しない。ソース・バイナリは`vendor/`に取得し、Gitには含めない。

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
