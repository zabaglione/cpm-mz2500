# CP/M Plus for SHARP MZ-2500

SHARP MZ-2500向けのCP/M 3（CP/M Plus）移植です。MZ-2500移植版の番号は
**v3.0.0**、使用するDRI純正BDOSの番号は **3.1** です。表示だけを変更した
2.2版ではなく、BDOS・CCP・BIOSインタフェースをCP/M Plusへ置き換えています。
以前のCP/M 2.2版は **v1.3.2タグ**に保存しています。

## 構成

- **非バンク版CP/M Plus**。標準RAMで動作し、EMMは必須ではありません。
- 80×25テキスト。ADM-3A、ANSI/VT100サブセット、TeleVideo拡張の画面制御を継承。
- **A:/B:** 2DDフロッピー（640KB、システム予約領域を除く容量608KB）。
- **C:/D:** SASI HDD（8MBパーティション×2）。EH-SASIによるHDD単独起動に対応。
- **E:** MZ-1R37 EMM RAMディスク（ファイル容量620KB）。EMMの内容はリセットで保持。
- CCPを標準RAMの物理バンク08hに保存し、ウォームブートで再読込。
  EMMなしでもコマンドプロンプトへ復帰します。
- CCPのローダーが常駐した通常状態で、TPAは約48.75KB。RSX等でさらに減少します。

## ビルド

Python 3と`z80asm`が必要です。macOSでは`brew install z80asm`で導入できます。

```sh
make fetch
make disks
make test
```

`make fetch`はCP/M Plusのバイナリ・ソース、フォント、開発ツールをSHA256照合付きで
取得します。取得物はGit管理外の`vendor/`に置きます。CP/M 2.2の取得・変換経路は
廃止しました。ビルド時にも展開済みCP/Mバイナリの改変を検出します。

| 生成物 | 内容 |
|---|---|
| `build/cpm_boot.d88` | CP/M Plus起動FD、標準ユーティリティ、PUTSYS |
| `build/cpm_data.d88` | 空のデータFD |
| `build/cpm.hdd` | HDD単独起動用、C:システム・開発ツール、D:言語処理系 |
| `build/cpm_tools.d88` | 開発ツール＋CBASIC |
| `build/cpm_langs1.d88` | Pascal/MT+ |
| `build/cpm_langs2.d88` | PL/I-80＋BDS C |

標準ユーティリティにはPIP、ED、SUBMIT、DIR、TYPE、ERASE、RENAME、SHOW、SET、
SETDEF、DUMP、HEXCOM、SID、HELPなどを含みます。2.2版のSTATやXSUBの代わりに
Plus版のコマンドを使用します。開発・言語ツールは従来の取得物で、全処理系の
Plus上での動作確認を完了したという意味ではありません。

## エミュレータでの実行と検証

外部のMZ-2500エミュレータに`build/cpm_boot.d88`をFD1として指定します。
このリポジトリにはエミュレータやROMを含めません。

```sh
/path/to/mz2500w-cli --disk-a build/cpm_boot.d88 \
  --frames 1800 --type 'SHOW\r:1000' --screen-report

python3 tools/verify_runtime.py --emulator /path/to/mz2500w-cli
```

HDD単独起動も検証する場合は、所有するROMを指定します。

```sh
python3 tools/verify_runtime.py --emulator /path/to/mz2500w-cli \
  --rom-dir /path/to/mz2500-roms --sasi-rom /path/to/sasirom.bin
```

実行結果・保存ディスク・画面は`build/qa/`に出力します。検証プログラムは実際の
Z80/BDOS呼び出しでバージョン31h、SCB、ファイル名解析、複数レコード入出力、
ランダム読込、フラッシュを確認します。PIPの70,000バイトコピーは保存ディスクを
ホスト側で読み直し、バイト比較します。SUBMIT、EMM保持、PUTSYSの書込範囲、
外部ROMを使ったHDD起動も別シナリオで確認します。

**検証範囲:** 静的テストとネイティブエミュレータでの実行を対象としています。
今回のPlus版は実機・ブラウザでは未検証です。既存Webサイトの同梱HDDもこの作業では
更新していません。[移植仕様](docs/cpm3-port.md)に構成と判断根拠を記載しています。

## 2.2版のディスクとの関係

**Plus版では新規ディスクイメージを使用してください。** FDの予約トラックは6から8、
HDDは3から4へ変更しました。2.2版の既存ディスクをPlus版のデータドライブとして
使用することや、PUTSYSだけで2.2版HDDをPlus化することには対応しません。
既存SDカードへ書き込む前にカード全体をバックアップしてください。

Plus版で運用中のHDDを更新する場合のみ、新しいPlus起動FDをA:に入れて`PUTSYS`を
実行できます。A:/C:のPlusブートヘッダーを確認したうえで予約領域をコピーし、
起動ドライブをC:に設定します。C:のファイル領域とパーティション表は変更しません。
完了後、IPLボタンでコールドブートしてください。

実機FD用の変換例（この版の書込・実機起動は未実施）:

```sh
gw convert --format=luxor.640 build/cpm_boot.d88 cpm_boot.img
```

HDDは従来同様、22,437,888バイト、256バイト/ブロックのSASIイメージです。
EH-SASI環境へ新規イメージとして導入します。

## 対応範囲

- 非バンク構成です。バンク版固有の機能・大きなTPAは提供しません。
- RTC連動、プリンタ、補助入出力、DEVICEによる物理デバイス再割当は未対応です。
- フロッピー交換後はコマンドプロンプトでCtrl-Cを入力してください。
- カナ入力・F1–F10は未対応です。PCGを書き換えるアプリの後はIPLで復旧します。
- 物理RAMバンク08hはCCPキャッシュとして予約しています。
- 過去のゲーム動作確認は2.2版の記録です。[ゲームカタログ](GAMES.md)を参照してください。

## ライセンス

移植コードはMIT、CP/M PlusおよびDRI製品はDRDOS, Inc.の2022-07-07許諾によります。
[LICENSES.md](LICENSES.md)に取得元・許諾・変更内容をまとめています。
