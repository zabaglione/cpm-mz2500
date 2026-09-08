# バンク転送の最適化（v3.1.2）

共通BIOSのMOVEを、同一バンクではLDIR、異なるバンクでは最大128バイトの
共通バッファ経由に変更しました。片側が共通領域なら、そのバッファを経由せず
直接転送します。128バイト境界で区切るため、E000hの共通領域境界と0000hへの
折り返しにも対応します。重なった領域は従来どおり前方向のバイトコピーです。

同じプロジェクト所有のネイティブエミュレータを使い、6MHz相当のCPUサイクル数で
比較しました。通信・展開時間とホストPCの描画遅延は含みません。起動は各版の
新規HDD、ドライブ切り替えは同じ空のフォーマット済みB:を使用した単回測定です。

| 操作 | 最適化前 | 最適化後 |
|---|---:|---:|
| HDD起動からC>まで | 12.47秒 | 7.05秒 |
| 初回A:→B: | 1.59秒 | 0.97秒 |
| 再選択A:→B: | 0.45秒 | 0.45秒 |

切り替え測定には一定のキー入力時間を含みます。比較用CP/M 2.2のHDD起動は6.54秒でした。
未フォーマット媒体の読込失敗を解消する変更ではありません。実機での速度は未測定です。

MOVEの146ケースは、実際にビルドした共通BIOSを独立したメモリーモデルと
外部のMIT Z80コアで実行します。バンク0/1、共通領域境界、アドレス折り返し、
重なり、HL/DE/BCの結果、呼出元バンクへの復帰、XMOVEの一回限りの指定を検証します。

```sh
cc -O2 -I /path/to/emulator/vendor/z80 -c /path/to/emulator/vendor/z80/z80.c -o build/z80-test.o
c++ -O2 -std=c++17 -I /path/to/emulator/vendor tools/verify_move.cpp build/z80-test.o -o build/verify_move
build/verify_move build/bios_common.bin
```

起動・ドライブ切替の測定ランナーは`tools/measure_performance.cpp`です。
`tools/verify_format.cpp`と同様に外部エミュレータのネイティブコアへリンクし、
`measure_performance build/cpm.hdd build/cpm_boot.d88 build/cpm_data.d88`で実行します。
