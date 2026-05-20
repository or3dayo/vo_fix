# vo_fix

SUNO等のAI歌声を人間っぽくする後処理ツール。

「均一すぎる AI ピッチ・音量に、人間の声がもつ自然な揺らぎを足し戻す」のが本体の仕事です。
声質変換そのもの (RVC) は専用ツール (Applio など) に任せて、vo_fix は仕上げに特化します。

## できること

- **ピッチ揺らぎ注入**: pyworld で f0 を分解 → 微小な drift を足して再合成。均一すぎるピッチに人間味
- **ビブラート追加・速度変調**: 既存ビブラートにムラを足す or 0 → 数 cents の自然な揺れを追加
- **アンプリチュード shimmer**: 音量に有機的な揺らぎ
- **エフェクトチェーン** (pedalboard): ハイカット / プレゼンス / サチュレーション / リバーブ
- **iZotope RX 前処理** (オプション): Voice De-noise / De-click を VST3 経由で実行
- **CLI と Gradio UI** 両対応
- 4 プリセット: `off` / `natural` / `intimate` / `polished`

## おすすめワークフロー

```
SUNO (歌声生成)
   ↓ Stem 書き出し (vocal only wav)
Applio (RVC で声質変換)  ← 必要なら
   ↓ 変換後 wav
vo_fix (揺らぎ + ミックス処理)
   ↓
完成
```

声質変換が要らない場合は、SUNO の vocal stem を直接 vo_fix に渡してもOK。

## セットアップ

**Python 3.11 が必要** (依存ライブラリの wheel 都合)。

```powershell
cd C:\dev\vo_fix
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 使い方

### Gradio UI (推奨)

```powershell
.\.venv\Scripts\python.exe app.py
```

ブラウザで http://localhost:7860 が開きます。
プリセットを選んで、必要に応じてスライダーで微調整 → 「変換」ボタン。

### CLI

```powershell
.\.venv\Scripts\python.exe cli.py --input samples/vocal.wav --output out/vocal_human.wav --preset natural
```

主なオプション (すべて省略可、プリセット値が使われる):

| オプション | 内容 | 既定 (natural) |
|---|---|---|
| `--preset {off,natural,intimate,polished}` | 出発点 | `natural` |
| `--jitter-cents N` | ピッチ揺らぎ stddev (cents) | 8 |
| `--shimmer F` | アンプ揺らぎ (0–0.1) | 0.03 |
| `--vibrato-depth N` | 追加ビブラート深さ (cents) | 0 |
| `--vibrato-rate N` | ビブラート速度 (Hz) | 5.5 |
| `--high-cut HZ` | ハイカット | 9000 |
| `--presence-db DB` | 3kHz ブースト | 0.5 |
| `--saturation F` | サチュレーション (0–1) | 0.15 |
| `--reverb-mix F` | リバーブ wet (0–1) | 0.08 |
| `--reverb-room F` | リバーブ room size | 0.35 |
| `--seed N` | 揺らぎの再現用 seed | random |
| `--no-humanize` | 揺らぎ処理スキップ | - |
| `--no-effects` | エフェクトスキップ | - |

### iZotope RX 前処理(オプション)

RX 8 以降を持っている場合、Voice De-noise と De-click を humanize の前に挟めます。
ライセンスが認証済みなら追加セットアップ不要、`--rx-denoise` / `--rx-declick` を渡すだけ。

```powershell
# Voice De-noise 8dB + De-click sensitivity 4 で前処理
.\.venv\Scripts\python.exe cli.py -i in.wav -o out.wav --preset natural --rx-denoise 8 --rx-declick 4
```

| オプション | 内容 | 推奨値 |
|---|---|---|
| `--rx-denoise DB` | Voice De-noise reduction | 4–10 dB |
| `--rx-declick SENS` | De-click sensitivity | 2–5 |
| `--rx-plugin-dir PATH` | VST3 ディレクトリ上書き | デフォルト `C:\Program Files\Common Files\VST3\iZotope\` |

**処理順**: RX クリーニング → humanize → エフェクト。先にノイズを取って、後で揺らぎを足すのが正解(逆だと De-noise が揺らぎをノイズ扱いして削ってしまう)。

**未認証/未インストール時**: 警告ログを出してRXステップをスキップ、残りの処理は続行します。クラッシュしません。

Gradio UI からは「iZotope RX 前処理」アコーディオンを開いてチェックボックスで有効化。

### プリセットの傾向

- **off**: 何もしない (リサンプル + 正規化のみ)。比較用
- **natural**: 自然な揺らぎ + 軽いミックス。デフォルト
- **intimate**: 揺らぎ強め + リバーブ深め。バラード向け
- **polished**: 揺らぎ控えめ + 高域明るめ + リバーブ薄め。ポップス・前面向け

## ファイル構成

```
vo_fix/
├── humanize.py      # pyworld f0 jitter + amp shimmer
├── effects.py       # pedalboard EQ/saturation/reverb
├── vst.py           # iZotope RX VST3 ローダー
├── pipeline.py      # オーケストレーション + プリセット
├── io.py            # wav 読み書き
├── rvc.py           # スタブ (Applio 連携を推奨)
└── __init__.py
cli.py               # click ベースの CLI
app.py               # Gradio UI
scripts/smoke_test.py # 合成音源で end-to-end 動作確認
```

## 試運転

サンプル wav が手元になくても、合成された「機械的な」歌声で動作確認できます:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

`out/` 配下に各プリセットの結果が出力されます。`00_input_robotic.wav` (素材) と
`01_natural.wav` を聞き比べると揺らぎ効果が確認できます。

## なぜ RVC を内蔵しないのか

短く: **Windows + Python での RVC 依存解決が苦行だから**。

- `fairseq==0.12.2` (RVC が要求) は Windows wheel がなく、Visual C++ ビルドツール (5GB+) が必要
- `omegaconf==2.0.6` (旧版) は最新 pip でメタデータエラー
- 各 RVC フォークは個別に互換性問題

Applio (https://applio.org/) はこれらを全部解決済みのワンクリックインストーラを配布しているので、声質変換はそちらに任せて、vo_fix は「揺らぎ + 仕上げ」に集中する設計です。

将来安定した pip RVC パッケージが出たら `vo_fix/rvc.py` を差し替えるだけで全体が動くよう、CLI/UI 側にはすでに `--rvc-model` フックを残してあります。

## ライセンス

GPL-3.0 (詳細は [LICENSE](LICENSE))。

依存ライブラリの `pedalboard` (Spotify) が GPL-3.0 のため、本プロジェクト全体も GPL-3.0 で配布しています。フォーク・改造は自由ですが、配布する場合は派生物も GPL-3.0 互換ライセンスでソース公開してください。

## トラブルシューティング

- **`pyworld` の import エラー**: Python 3.11 を使っているか確認。3.12+ では wheel がない
- **音量が大きすぎる/クリップする**: 出力前に正規化していますが、`--saturation 0` と `--reverb-mix 0` で素直な処理だけにできます
- **ピッチがおかしい**: pyworld の f0 検出は無声区間で時々ハマる。`--jitter-cents 0` で揺らぎを切り、エフェクトだけ使うのも手
