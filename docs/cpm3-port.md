# MZ-2500 CP/M Plus移植仕様

## ベースと版番号

CP/M 2.2版の`v1.3.2`（コミット`128c5b0`）から移植。
新しい移植版番号は`v3.1.0`。DRIのバンク版CP/M Plus 3.1 BDOSとCCPを使用する。
BDOS Function 12が返す値は31hで、30hへの偽装は行わない。

## 参照資料

- [Digital Research CP/M releases](https://www.seasip.info/Cpm/software/dri.html)
  — John ElliottによるDRIソースからのビルド、2026-06-07版。
- [DRI CP/M 3 System Guide](https://www.cpm.z80.de/manuals/cpm3-sys.pdf)
  — CP/M 3のシステムインタフェース資料。
- 配布元の`cpm3src_unix.zip`に含まれるDRIの`gencpm.plm`、`cpmbdos1.asm`、
  `bdos30.asm`、`bioskrnl.asm`、`scb.asm`、`ccp3.asm` —
  バンク構成のメモリー配置、SPRヘッダー、BIOSエントリー、DPH/DPB/BCB、
  SCB、ローダー再入仕様を確認。

EmuZ/CSCPソースは使用しない。MZ-2500依存のI/Oは既存のプロジェクト所有BIOSを
再利用し、外部エミュレータとは入力ディスク・キー入力・出力画面・保存ディスク
による比較だけを行う。エミュレータやROMはこのリポジトリに含めない。

## メモリー配置

| 領域 | 用途 |
|---|---|
| バンク1、0100h–DFFFh | TPA、CCP実行領域。物理00h–06h |
| バンク0、0000h–DFFFh | システム領域。物理08h–0Eh |
| バンク0、8000h/8100h/8400h | IPL入口、フォント、コールド初期化 |
| バンク0、8500h–A4FFh内 | ハードウェアBIOS、RTC変換、ディスクバッファ |
| バンク0、A500h–B17Fh | CCP 3,200バイトの保存コピー |
| バンク0、B200h–DFFFh | バンク版BDOS |
| 共通、E000h–E1FFh | TPAの上端（ローダー・RSXの常駐で減少） |
| 共通、E200h–E7FFh | 常駐BDOS、エントリーE206h、SCB E79Ch |
| 共通、E800h以降 | 33エントリーBIOS、バンク切替、共通スタック |

共通領域E000h–FFFFhは物理07hに固定します。IPLPROは物理0Ch/0Dh/0Eh/07hの
4バンクを読み込み、8000hへ入ります。CPMLDR/GENCPM出力のCPM3.SYSを経由せず、
固定構成でネイティブIPLPROから起動します。`resbdos3.spr`と`bnkbdos3.spr`の
再配置ビットを読み、FC/FFおよびFB/FD/FFの外部ページ参照をBDOS・SCB・BIOSへ解決します。

SELMEMはBC/DE/HLを保持して7ブロックを切り替えます。切替を直接呼ぶコード・
スタックは共通領域に置く必要があります。XMOVEの指定は次のMOVEだけに適用し、
MOVEは専用共通スタックでコピー後に元のバンクへ戻ります。ハードウェアBIOSは
共通の入口からバンク0へ切り替えて実行し、呼出元へ戻します。SETBNK/SETDMAで
指定されたDMAは共通の128バイトバッファを介して転送します。割込みを使わない
ポーリング構成で、共通ゲートウェイは非再入です。

ウォームブートではBDOSを上書きしない。SCBのMXTPAを使って0005hの呼び出し先を
再設定し、Plusローダー/RSXチェーンを保持する。BIOS側の選択中ドライブも保持する。
これをA:に初期化すると、常駐BDOSがC:を選択済みと考えたままA:を読み、HDD上の
次のコマンドを見失うため、SHOW→PIPの連続実行を回帰検証に含める。

## ディスク

CP/M 3の33エントリーBIOSと25バイトDPHを実装する。DPBは17バイトに拡張し、
PSH/PHMを0とする。BDOSには128バイトレコードを提示し、既存BIOSが256バイト物理
セクターへまとめる。バンクBDOS用にディレクトリー用とデータ用のBCBとリスト先頭ポインターを用意し、
ハッシュテーブルは無効とする。FLUSHは物理書込エラーをBDOSへ返す。

FDはOFF=10、DSM=299、HDDはOFF=5、DSM=2037。EMMはOFF=2、DSM=311を維持する。
新しいブート領域が2.2版・v3.0.0のファイル領域と重なるため、旧イメージの直接再利用や
自動変換は行わない。PUTSYSはバンク版の起動ヘッダー・ロード先を持つA:/C:だけを対象とする。

## RTC

SHARP MZ-2500 I/OマップのCChポートを使用し、レジスター番号をA11:A8へ出力する。
[Ricoh RP/RF/RJ5C15 datasheet EK-086-9908](https://www.cryptomuseum.com/crypto/philips/px2000/files/RP5C15.pdf)
の6–7ページに従う。MODEのD3でカウンターを一時停止し、D0でレジスターバンクを
選ぶ。24時間制の設定はバンク1のAh、**D0**である。

BIOS TIMEはSCB+58hの5バイト（日数LE、BCD時分秒）とRTCを相互変換する。
1978-01-01を日数1とし、RTCの2桁年を1978–2077年へ割り当てる。範囲外・不正BCD・
不正月日はA=1で拒否する。読出しは12/24時間制に対応し、書込は24時間制に統一して
うるう年カウンター・曜日・秒分周リセットを設定する。ホストOSの時計は変更しない。
BDOS 104の引数は4バイトで秒を0に設定し、105は4バイトを返して秒をAに返す。
アラーム・周期割込みは使用しない。

## 検証の区別

- 静的: ピン留めされた取得物、SPRの再配置、DPB容量、ブート領域の非重複、
  HDDの起動ドライブパッチ、ファイルシステムの複数エクステント等。
- 実行: 外部ネイティブエミュレータでZ80コードを実行。BDOS 31h、SCB、PARSE、
  複数レコード・ランダムI/O・FLUSH、PIP大容量コピー、SUBMIT、EMM保持、
  拡張なし起動、PUTSYS、所有ROMを用いたHDD単独起動。加えてSELMEMのレジスター保持、
  XMOVE/MOVE、上位TPA、RTCの1978–2077年の代表9日付・うるう日・2000年・12時間制の正午/午前0時/午後11時を検証。
- 実機/ブラウザ: 今回のPlus版は未検証。2.2版の実機記録はPlus版の証明に転用しない。

`tools/verify_runtime.py`が再現用エントリー。実行ログ・画面・書込後イメージは
Git管理外の`build/qa/`へ保存する。ROMを渡さない実行はHDD単独起動を省略する。
