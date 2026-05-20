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

### 必要なもの

- **Python 3.11** (依存ライブラリの wheel 都合。3.12+ では pyworld 等の wheel が無くビルド失敗)
- **Git** (clone するため。無ければ `winget install --id Git.Git` か https://git-scm.com/download/win から)
- **Windows** (RX VST 統合は Windows パス前提。macOS/Linux でも本体は動くが RX 部分は要パス変更)

### 1. ダウンロード(git clone)

```powershell
cd C:\dev               # 配置先(下記「配置先の推奨」参照)
git clone https://github.com/or3dayo/vo_fix.git
cd vo_fix
```

> ZIP DL (Code → Download ZIP) でもOKですが、後から `git pull` で更新できなくなるので **git clone を強く推奨** します。

### 2. Python 3.11 を準備

Python 3.13+ が入っていれば py launcher 経由で 3.11 を追加できます:

```powershell
py install 3.11
py -3.11 --version    # 3.11.x が出ればOK
```

3.13 以前を使っている場合は https://www.python.org/downloads/release/python-3119/ から手動 DL。インストール時 **Add to PATH** にチェック。

### 3. venv 作成と依存インストール

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

PowerShell の実行ポリシーで Activate.ps1 が弾かれる場合:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

(これは一度だけでOK。以後の Python セッションすべてに効きます)

### 配置先の推奨

| 場所 | おすすめ度 | 理由 |
|---|---|---|
| `C:\dev\vo_fix\` | ◎ 第一選択 | 短い・スペースなし・OneDriveの外。安牌 |
| `C:\repos\vo_fix\`, `D:\dev\vo_fix\` | ◎ 同等 | 好みで |
| `C:\Users\<name>\Documents\...` | ⚠️ 注意 | 多くの日本語Windowsで OneDrive 同期対象。`.venv` (数百MB) も同期されて遅くなる |
| `C:\Users\<name>\OneDrive\...` | ❌ 避ける | 同上、`pip install` 中にファイルロック衝突で失敗することも |
| `C:\Program Files\...` | ❌ 避ける | UAC で `pip install` が弾かれる |
| パスに日本語/スペース | ⚠️ 注意 | 通常動くが一部C拡張で稀にエラー |

### 更新の取り込み(後日)

vo_fix が更新されたら **再DL不要**、`git pull` で最新化:

```powershell
cd C:\dev\vo_fix
git pull
```

依存関係が増えていたら追加で:

```powershell
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

| プリセット | キャラ | jitter / vib / shimmer | reverb / 高域 | こんなとき |
|---|---|---|---|---|
| **off** | 無加工 | 0 / 0 / 0 | OFF / 素通り | 処理前と比較したい / 既に完成している素材 |
| **natural** | 自然デフォルト | 8 / 0 / 0.03 | 控えめ / 9kHz | 迷ったらコレ。ほぼ全用途で破綻しない |
| **intimate** | しっとり | 12 / 6 / 0.05 | 深め / 8.5kHz | バラード / ささやき / ジャズボーカル / アコースティック |
| **polished** | 前に出るポップ | 4 / 0 / 0.02 | 薄め / 10kHz + プレゼンス | アップテンポなポップス / EDMボーカル / 前面定位 |

数値は順に「ピッチjitter (cents) / ビブラート深さ (cents) / shimmer」。

### パラメータリファレンス

#### Humanize (揺らぎ)

| パラメータ | 範囲 | 効果 |
|---|---|---|
| `--jitter-cents` | 0–30 | ピッチの微小揺れ。**0=AI素のまま** / 8=自然 / 15+=酔った歌い手。100 cents = 半音 |
| `--vibrato-depth` | 0–30 | 強制付与するビブラート深さ。**0=既存だけ揺らす** / 3-8=自然 / 15+=演歌・オペラ |
| `--vibrato-rate` | 3–8 Hz | ビブラートの揺れる速さ。**5-6Hzが人間的** / 7+で神経質 / 4でゆったり |
| `--shimmer` | 0–0.1 | 音量の細かい揺れ。**0=平坦(機械的)** / 0.03=自然な息づかい / 0.08+=不安定で生々しい |

#### Effects

| パラメータ | 範囲 | 効果 |
|---|---|---|
| `--high-cut` | 4000–18000 Hz | ここより上の高域を削る。**AI特有のシャリつき抑制**。低いほど暗く / 高いほど明るく。8-10kHz目安 |
| `--presence-db` | -6 ~ +6 dB | 3kHz付近(明瞭度帯)のEQ。**+で前に出る/抜けが良くなる** / -で奥に引っ込む/まろやか |
| `--saturation` | 0–1 | テープ風倍音歪み。**0=デジタルクリア** / 0.15=温かみ / 0.4+=ロック・ローファイ寄り |
| `--reverb-mix` | 0–1 | 空間の響き量(wet)。**0=密室** / 0.1=部屋 / 0.3+=お風呂・ホール |
| `--reverb-room` | 0–1 | 響く空間の大きさ。**0=小箱(短い残響)** / 0.5=居室 / 1=大ホール(長い余韻) |

#### iZotope RX 前処理

| パラメータ | 範囲 | 効果 |
|---|---|---|
| `--rx-denoise` | 0–20 dB | Voice De-noise の reduction 量。**0=オフ** / 4-6=軽い / 8-10=しっかり / 15+=声まで削れて不自然 |
| `--rx-declick` | 0.5–10 | De-click sensitivity。**0.5=オフ寄り** / 2-3=控えめ / 4-5=標準 / 7+=やり過ぎ |

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

### セットアップ系

| 症状 | 原因と対処 |
|---|---|
| `git: command not found` | Git未インストール。`winget install --id Git.Git` |
| `git clone` で認証ダイアログ | publicリポジトリなので本来不要。GitHubに以前ログインしてた認証情報が古い可能性。キャンセルで通ることも |
| `Permission denied (publickey)` | SSH URLを使っている。HTTPSの `https://github.com/or3dayo/vo_fix.git` に変更 |
| `fatal: destination path 'vo_fix' already exists` | 同名フォルダが既にある。別の場所で clone するか既存を削除 |
| `py -3.11` が動かない | Python 3.11未インストール。`py install 3.11` で追加(py launcher必須) |
| `Activate.ps1` が `スクリプトの実行が無効` | `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` を一度実行 |
| `pip install` が途中で失敗 | OneDrive配下に置いていないか確認。ファイルロック衝突の主因。`C:\dev\vo_fix\` 等へ移動 |
| `pyworld` の import エラー | Python 3.11 を使っているか確認。3.12+ では wheel がなくビルド失敗 |

### Git 運用系

| 症状 | 対処 |
|---|---|
| `! [rejected] main -> main (fetch first)` | リモートに別のコミットがある。`git pull --rebase` で取り込んでから push |
| diverge した(両方コミットがある) | `git pull --rebase` でコンフリクト無ければ吸収。コンフリクトしたら手で解決 |
| Web UI 編集で diverge した | `git push --force-with-lease` でローカル優先(誤操作の場合のみ) |
| 共有先がpullできない(force push後) | `git fetch && git reset --hard origin/main` で同期 |

### 音処理系

| 症状 | 対処 |
|---|---|
| 音量が大きすぎる/クリップする | 出力前に正規化されますが、`--saturation 0 --reverb-mix 0` で素直な処理だけにできます |
| ピッチがおかしい / ノイズが乗る | pyworld の f0 検出が無声区間で時々ハマる。`--jitter-cents 0 --vibrato-depth 0` で揺らぎを切り、エフェクトのみにする |
| 揺らぎが効いてない感じ | 元素材が既に揺れている可能性。`--preset off` と比較するとわかる。または `--jitter-cents 15` まで強める |
| RXが効かない/警告ログだけ出る | iLok/Product Portalで認証されているか、VST3パスが合っているか確認。`find_rx_plugins()` で検出状況確認可 |
| Gradio が `localhost:7860` を開けない | 既に別アプリが7860使用中。`app.py` 末尾の `.launch()` を `.launch(server_port=7861)` に |
