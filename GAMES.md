# ゲームカタログ — MZ-2500版CP/Mで遊ぶ

MZ-2500版CP/M 2.2で**実際に動作確認したゲーム**の一覧と、遊ぶまでの
手順です。ゲームは本体イメージやリリースには一切同梱していません。
かわりに、**ご自分のマシン上で起動フロッピーを組み立てる**スクリプトを
用意しています（取得は全てSHA256検証付き）。権利表記のない当時の
ソフトについては、生成したディスクをご自身の私的利用の範囲でお使い
ください。

## 使い方（共通）

必要なのは **Python 3 だけ**です（CP/M本体はローカルでビルド済みなら
それを、なければリリース版を自動取得します）:

```
git clone https://github.com/zabaglione/cpm-mz2500.git
cd cpm-mz2500
python3 tools/make_game_disk.py --list      # カタログ表示
python3 tools/make_game_disk.py ladder      # 例: build/ladder.d88 が完成
```

できあがったディスクは起動可能フロッピーです:

- **ブラウザで** —
  [ブラウザ版エミュレータ](https://zabaglione.github.io/mz2500-web-emulator/)
  を開き、d88ファイルを画面にドラッグ&ドロップ。CP/Mが起動したら
  `A>` に起動コマンドを入力。ディスクへの書き込み（セーブ・ハイスコア）は
  ブラウザ内に保存され、次回も続きから遊べます（別のディスクを入れる前に
  残したいものはFDスロットのSAVEボタンで書き出せます）
- **実機で** — READMEの「実機で — フロッピー」の手順どおり書き込んで
  起動し、`A>` に起動コマンドを入力

## 動作確認済みタイトル

| ビルド名 | タイトル（年） | ジャンル | 起動コマンド | 操作 |
|---|---|---|---|---|
| `ladder` | Ladder (1982) | アクション | `LADDER` | W/A/S/D移動、SPACEジャンプ |
| `catchum` | CatChum (1982) | アクション | `CATCHUM` | W/A/S/D移動 |
| `rogue` | Rogue 1.7 (1985) | ローグライク | `ROGUE` | h/j/k/l移動（斜め y/u/b/n） |
| `inthedark` | In The Dark (2022) | ローグライク | `ITDARK80` | w/a/s/d移動、q終了 |
| `advent` | Colossal Cave Adventure | アドベンチャー | `ADVENTUR` | 英語2語コマンド入力 |
| `flap` | FLAP CP/M | アクション | `FLAPCPM` | SPACEで飛ぶ、q終了 |

### Ladder — ASCII版ドンキーコング

梯子を上り、転がる岩を避けて `$` を目指すアクション。文字端末で
動いていること自体が楽しい、CP/Mゲームの代表格です。

- メニューで `P`=開始、`L`=難易度変更、`I`=説明
- **端末（ADM 3A）とWASDキーは設定済み**の状態でディスクが作られます。
  変えたい場合は `LADCONF` を実行してください（同梱済み）
- ハイスコアはディスクに保存されます

### CatChum — ASCII版パックマン

ドットを食べ尽くし、パワーエサで猫（`A`）に反撃する迷路アクション。
Ladderと同じく端末・キー設定済み。`1`=1人プレイ、`C`=再設定（`CATCONF`）。

### Rogue 1.7 — ローグライクの原点

自動生成ダンジョンで「Funidoogの魔除け」（20階より下）を目指します。
ライセンス表記のない当時のソフトのため、お手元取得方式です。

- コマンド一覧は `TYPE ROGUE.DOC`
- セーブは `S`（既定名は `Y` で確定）。**再開は `ROGUE ROGUE.SAV`**
  とファイル名を引数に付けます。読み込むとセーブは消えます（本家仕様）

### In The Dark — 現代のCP/Mローグライク

[Kian Ryan氏作](https://github.com/kianryan/InTheDark)（2022年、
MITライセンス）。灯り `#` を頼りに宝 `$` を集めて次の階へ。灯りが
尽きると Grue `"` が闇から迫ってきます。

### Colossal Cave Adventure — テキストアドベンチャーの始祖

洞窟を探索し謎を解く原典（Z80移植版、[IF Archive](https://www.ifarchive.org/indexes/if-archive/games/cpm/)収蔵）。
`GO IN` のような英語1〜2語で指示します（単語は先頭5文字で判定）。
`HELP` でヒント、`INFO` で終了方法などの案内が出ます。

### FLAP CP/M — Flappy Bird型

[ivang78/cpm-games](https://github.com/ivang78/cpm-games)収載。
起動時の端末選択は **1（ANSI）でカラー表示**になります
（2=VT102は白黒）。

## 自分のMZでビルドするゲーム

Turbo Pascal 3.0でしか配布されていないソースのゲームを、**同梱の
Pascal/MT+でMZ-2500自身にコンパイルさせる**モードです。スクリプトが
ソースをMT+向けに機械変換し、コンパイラごと1枚のディスクに載せます:

```
python3 tools/make_game_disk.py 2048       # → build/2048.d88
python3 tools/make_game_disk.py balls      # → build/balls.d88
python3 tools/make_game_disk.py evas10n    # → build/evas10n.d88
```

起動したら一度だけ:

```
A>SUBMIT MAKE
```

数分待つとMZがコンパイルとリンクを終えます（コンパイラの進行表示が
流れるのを眺めるのも一興です）。以後は `G2048` と打つだけ。生成された
G2048.COMはディスクに残るので、ビルドは初回のみです（ブラウザ版なら
ブラウザ保存に残ります）。

### 2048 — `SUBMIT MAKE` → `G2048`

[ivang78/cpm-games](https://github.com/ivang78/cpm-games)収載の
CP/M版2048。盤面サイズは4か5を選択、W/A/S/D移動、Rで新規、ESCで終了。
タイルは段位ごとに色分けされます。

### Balls — `SUBMIT MAKE` → `BALLS`

同じくivang78収載のカラーボールパズル（5個並べると消える系）。
W/A/S/Dでカーソル/ボール移動、SPACEで掴む・置く、ESCで終了。
白い盤面の上を5色のボールが転がります。

### EVAS10N — `SUBMIT MAKE` → `EVAS10N`

[Marco's Retrobits作のブロック崩し](https://github.com/marcosretrobits/EVAS10N.PAS)の
ivang78 ANSI版。起動時の端末選択は1（ANSI）でカラー表示。
z=左、x=右、qで終了。5色のレンガ帯を打ち抜いて脱出（Free!）を目指します。

いずれもコンパイル済みの.COMはディスクに残るため、2回目以降は
コマンド名を打つだけで起動します。

**Zork I**（Infocom, 1982）— CP/M版（Release 25）が本機で動作すること
を確認済みです（文章解析・データファイル読込とも問題なし）。ただし
権利が現在も存続する商用作品のため、取得スクリプトは提供しません。
正規の現行入手先は
[GOG](https://www.gog.com/en/game/the_zork_anthology) /
[Steam](https://store.steampowered.com/app/570580/Zork_Anthology/)
です（CP/M版バイナリ自体は含まれない点に注意）。すでにCP/M版の
`ZORK1.COM` と `ZORK1.DAT` をお持ちなら、汎用オプションで
ディスク化できます:

```
python3 tools/make_game_disk.py --local ZORK1.COM ZORK1.DAT --output build/zork1.d88
```

（`--local` は手持ちの任意のCP/Mソフトをブータブルディスクにする
汎用機能です）

## 未検証（メモ）

- **Super Star Trek** — MBASIC（Microsoft BASIC-80）の別途入手が必要
- **Nemesis**（1981年の商用RPG）— 権利未整理のため保留

## うまく動かないときは

- フロッピーを入れ替えたら **CTRL+C**（詳しくはREADMEの
  「フロッピーを入れ替えるとき」）
- 画面が乱れるソフトは、そのソフトの端末設定を
  **ADM-3A → TeleVideo 912/920 → VT-100(ANSI)** の優先順で選んで
  ください。本機のコンソールはこの3系統の制御コードを解釈し、
  ANSIカラー（文字色8色。背景色は文字色が白/黒のとき反転表示で近似）
  にも対応しています
- ゲーム中のキーがたまに効かないときは、もう一度押してください
  （画面描画の最中に押されたキーはCP/M 2.2のBDOSが読み捨てることが
  あります。当時からの仕様です）
