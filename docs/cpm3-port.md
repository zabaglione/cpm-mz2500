# MZ-2500 CP/M Plus移植仕様

## ベースと版番号

CP/M 2.2版の`v1.3.2`（コミット`128c5b0`）から移植。
新しい移植版番号は`v3.0.0`。DRIの非バンク版CP/M Plus 3.1 BDOSとCCPを使用する。
BDOS Function 12が返す値は31hで、30hへの偽装は行わない。

## 参照資料

- [Digital Research CP/M releases](https://www.seasip.info/Cpm/software/dri.html)
  — John ElliottによるDRIソースからのビルド、2026-06-07版。
- [DRI CP/M 3 System Guide](https://www.cpm.z80.de/manuals/cpm3-sys.pdf)
  — CP/M 3のシステムインタフェース資料。
- 配布元の`cpm3src_unix.zip`に含まれるDRIの`gencpm.plm`、`cpmbdos1.asm`、
  `bdos30.asm`、`bioskrnl.asm`、`scb.asm`、`ccp3.asm` —
  非バンク構成のメモリー配置、SPRヘッダー、BIOSエントリー、DPH/DPB/BCB、
  SCB、ローダー再入仕様を確認。

EmuZ/CSCPソースは使用しない。MZ-2500依存のI/Oは既存のプロジェクト所有BIOSを
再利用し、外部エミュレータとは入力ディスク・キー入力・出力画面・保存ディスク
による比較だけを行う。エミュレータやROMはこのリポジトリに含めない。

## メモリー配置

| アドレス | 用途 |
|---|---|
| 0100h | CCPを実行開始。トランジェント実行時はTPA |
| A000h | IPLPROの初期エントリー。初期化後はTPA |
| A100h | フォント初期データ |
| A400h | コールド初期化 |
| B000h–BC7Fh | 初回CCPイメージ。初期化後はTPA |
| C700h–E7FFh | 非バンクBDOS、エントリーC706h |
| E59Ch | SCB |
| E800h–FFFFh内 | MZ-2500 BIOS、ディスク用バッファ・作業領域 |
| 物理RAMバンク08h | CCP 3,200バイトのウォームブート用コピー |

IPLPROが物理バンク05h/06h/07hを読み込む。専用のCPMLDRを経由せず、ネイティブ
IPLPROから移植BIOSを起動する。汎用GENCPM出力のCPM3.SYSをロードする構成ではない。
SPRリロケーションビットが立つ上位アドレスを再配置し、FFhページ参照をBIOSへ
解決する。SCBの画面幅・行数・編集設定・初期ドライブを設定する。
CP/M 2.2版のBDOS Function 13パッチは廃止する。

ウォームブートではBDOSを上書きしない。SCBのMXTPAを使って0005hの呼び出し先を
再設定し、Plusローダー/RSXチェーンを保持する。BIOS側の選択中ドライブも保持する。
これをA:に初期化すると、常駐BDOSがC:を選択済みと考えたままA:を読み、HDD上の
次のコマンドを見失うため、SHOW→PIPの連続実行を回帰検証に含める。

## ディスク

CP/M 3の33エントリーBIOSと25バイトDPHを実装する。DPBは17バイトに拡張し、
PSH/PHMを0とする。BDOSには128バイトレコードを提示し、既存BIOSが256バイト物理
セクターへまとめる。非バンクBDOS用にディレクトリー用とデータ用のBCBを用意し、
ハッシュテーブルは無効とする。FLUSHは物理書込エラーをBDOSへ返す。

FDはOFF=8、DSM=303、HDDはOFF=4、DSM=2039。EMMはOFF=2、DSM=311を維持する。
新しいブート領域が2.2版のファイル領域と重なるため、旧イメージの直接再利用や
自動変換は行わない。PUTSYSはPlusヘッダーのあるA:/C:だけを対象とする。

## 検証の区別

- 静的: ピン留めされた取得物、SPRの再配置、DPB容量、ブート領域の非重複、
  HDDの起動ドライブパッチ、ファイルシステムの複数エクステント等。
- 実行: 外部ネイティブエミュレータでZ80コードを実行。BDOS 31h、SCB、PARSE、
  複数レコード・ランダムI/O・FLUSH、PIP大容量コピー、SUBMIT、EMM保持、
  拡張なし起動、PUTSYS、所有ROMを用いたHDD単独起動。
- 実機/ブラウザ: 今回のPlus版は未検証。2.2版の実機記録はPlus版の証明に転用しない。

`tools/verify_runtime.py`が再現用エントリー。実行ログ・画面・書込後イメージは
Git管理外の`build/qa/`へ保存する。ROMを渡さない実行はHDD単独起動を省略する。
