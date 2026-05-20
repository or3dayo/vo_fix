# vo_fix

SUNO等のAI歌声を人間っぽくする後処理ツール。

「均一すぎる AI ピッチ・音量に、人間の声がもつ自然な揺らぎを足し戻す」のが本体の仕事です。
声質変換そのもの (RVC) は専用ツール (Applio など) に任せて、vo_fix は仕上げに特化します。

---

## 🚀 クイックスタート

### 初回 (clone + セットアップ)

**Windows (PowerShell):**
```powershell
cd C:\dev
git clone https://github.com/or3dayo/vo_fix.git
cd vo_fix
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

**macOS / Linux:**
```bash
cd ~/dev
git clone https://github.com/or3dayo/vo_fix.git
cd vo_fix
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python app.py
```

ブラウザで http://localhost:7860 が開きます。

### 更新 (2回目以降)

**Windows:**
```powershell
cd C:\dev\vo_fix
git pull
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

**macOS / Linux:**
```bash
cd ~/dev/vo_fix
git pull
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python app.py
```

> Python 3.11 が必要。トラブル時は下記「[トラブルシューティング](#トラブルシューティング)」へ。  
> 詳しいセットアップ手順は「[セットアップ](#セットアップ)」へ。

---

## できること

- **ピッチ揺らぎ注入**: pyworld で f0 を分解 → 微小な drift を足して再合成。均一すぎるピッチに人間味
- **ビブラート追加・速度変調**: 既存ビブラートにムラを足す or 0 → 数 cents の自然な揺れを追加
- **アンプリチュード shimmer**: 音量に有機的な揺らぎ
- **フォルマント微変調 / 男声⇔女声 補正**: 声色のジェンダー方向の調整
- **子音強調・抑制**: トランジェント検出による歯切れ調整
- **自動ブレス挿入**: 無音区間検出 + 合成息継ぎ音
- **エフェクトチェーン** (pedalboard): 4バンドEQ / コンプレッサー / ディエッサー / コーラス / ハイカット / プレゼンス / サチュレーション / リバーブ
- **iZotope RX 前処理** (オプション): Voice De-noise / De-click を VST3 経由で実行
- **CLI と Gradio UI** 両対応
- 4 プリセット: `off` / `natural` / `intimate` / `polished` + ユーザーカスタム保存
- 操作ログ(変換ごとの差分を記録)
- **Spotify風ダークUI**(緑アクセント + ピル型ボタン + Inter フォント)

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
- **Git** (clone するため)
- **Windows / macOS / Linux** いずれも本体は動作。RX 統合は Windows と macOS で利用可能 (Linux は iZotope 非対応)

### Windows でセットアップ

#### 1. ダウンロード(git clone)

```powershell
cd C:\dev               # 配置先(下記「配置先の推奨」参照)
git clone https://github.com/or3dayo/vo_fix.git
cd vo_fix
```

> ZIP DL (Code → Download ZIP) でもOKですが、後から `git pull` で更新できなくなるので **git clone を強く推奨** します。Git が無い場合: `winget install --id Git.Git` か https://git-scm.com/download/win から。

#### 2. Python 3.11 を準備

Python 3.13+ が入っていれば py launcher 経由で 3.11 を追加できます:

```powershell
py install 3.11
py -3.11 --version    # 3.11.x が出ればOK
```

3.13 以前を使っている場合は https://www.python.org/downloads/release/python-3119/ から手動 DL。インストール時 **Add to PATH** にチェック。

#### 3. venv 作成と依存インストール

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

> **なぜ venv の python をフルパスで呼ぶの?**  
> 裸の `pip` や `python` は PATH 上の別バージョン(よくあるのは Microsoft Store経由でインストールされた Python 3.14 等)を掴むことがあります。それだと numpy 等が wheel 無しでビルド失敗します。フルパスなら確実に venv の 3.11 を使えます。

> Activate を使いたい場合: `.\.venv\Scripts\Activate.ps1`(`.\` ピリオド・バックスラッシュ・`.venv` の3パート)。実行ポリシーで弾かれたら一度だけ `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`。

### macOS でセットアップ

#### 1. ダウンロード(git clone)

```bash
cd ~/dev                # 無ければ mkdir -p ~/dev してから
git clone https://github.com/or3dayo/vo_fix.git
cd vo_fix
```

#### 2. Python 3.11 を準備

Homebrew が手軽:

```bash
brew install python@3.11
python3.11 --version    # 3.11.x が出ればOK
```

pyenv 派なら `pyenv install 3.11.9 && pyenv local 3.11.9` でもOK。

#### 3. venv 作成と依存インストール

```bash
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
```

Activate を使う場合: `source .venv/bin/activate`。

### Linux でセットアップ

Ubuntu/Debian の例:

```bash
sudo apt install python3.11 python3.11-venv git
git clone https://github.com/or3dayo/vo_fix.git
cd vo_fix
python3.11 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
```

RX VST3 は Linux 非対応(iZotope が Linux ビルドを提供していない)。揺らぎ + エフェクトのみ使用可能。

### 配置先の推奨

| OS | おすすめ | 避ける |
|---|---|---|
| **Windows** | `C:\dev\vo_fix\`, `D:\dev\vo_fix\` 等の短い場所 | `OneDrive\...`(同期衝突)、`Program Files`(UAC)、日本語/スペース入りパス |
| **macOS** | `~/dev/vo_fix`, `~/projects/vo_fix` | iCloud Drive 配下(`~/Documents/...` 等がそうなっていることあり) |
| **Linux** | `~/dev/vo_fix`, `~/src/vo_fix` | (特になし) |

クラウド同期フォルダ(OneDrive / iCloud / Dropbox)に `.venv` を置くと、数百MBの同期で重くなったり、ファイルロックで `pip install` が失敗します。

### Windows ⇄ macOS/Linux コマンド対応表

本ドキュメント中の Windows コマンドを他OSで読み替える表:

| Windows (PowerShell) | macOS / Linux (bash・zsh) |
|---|---|
| `py -3.11 -m venv .venv` | `python3.11 -m venv .venv` |
| `.\.venv\Scripts\Activate.ps1` | `source .venv/bin/activate` |
| `.\.venv\Scripts\python.exe app.py` | `./.venv/bin/python app.py` |
| `.\.venv\Scripts\python.exe cli.py ...` | `./.venv/bin/python cli.py ...` |
| `Remove-Item -Recurse -Force .venv` | `rm -rf .venv` |

Activate 済みの場合はどちらも `python app.py` でOK。

### 更新の取り込み(後日)

vo_fix が更新されたら **再DL不要**、`git pull` で最新化:

```bash
# Windows / macOS / Linux 共通
cd <vo_fixのパス>
git pull
```

依存関係が増えていたら(Windows):
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```
macOS / Linux:
```bash
./.venv/bin/python -m pip install -r requirements.txt
```

## 使い方

> 以下は Windows (PowerShell) の例。macOS / Linux の場合は `.\.venv\Scripts\python.exe` を `./.venv/bin/python` に読み替えてください。詳細は上の [Windows ⇄ macOS/Linux コマンド対応表](#windows--macoslinux-コマンド対応表) を参照。

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

### マイプリセット(カスタム保存・バックアップ)

スライダーをいい感じに調整したら、名前を付けて保存できます。次回起動時にもプリセット一覧に並びます。

1. UI を開く
2. 「マイプリセット (保存・削除・バックアップ)」アコーディオンを開く
3. 「保存名」に好きな名前を入れて 💾 ボタン
4. 上のプリセット一覧に `user: あなたの名前` が増える

**保存場所**: `~/.vo_fix/presets/<name>.json`
- Windows: `C:\Users\<user>\.vo_fix\presets\`
- macOS / Linux: `~/.vo_fix/presets/`

プロジェクトフォルダの外に保存されるので、**`git pull` で消えることはありません**。
JSON なのでテキストエディタで直接編集も可能。

組み込みプリセット(`off`/`natural`/`intimate`/`polished`)は削除不可、`user:` 付きのみ削除可。

#### バックアップ・別マシン共有

「マイプリセット」アコーディオン内の **バックアップ / 復元** セクション:

- **📦 全プリセットを zip でエクスポート**: 一括 zip 化 → ダウンロード可能
- **📥 zip からインポート**: zip をアップロード → 復元(上書きトグルあり)

別 PC への移行・同僚とのプリセット共有・万一の事故対策に使えます。

### 操作ログ

UI右側の「操作ログ」パネルに、変換ごとに以下が記録されます:

- 入力ファイル名・処理時間
- 使ったプリセット名
- そのプリセットから**何を上書きしたか**(プリセット値そのままなら省略)

これで「あの設定どうやって作ったっけ?」が後から辿れます。
セッションログは `~/.vo_fix/logs/session-YYYYMMDD.jsonl` にも追記され、JSON Lines 形式なので集計・分析にも使えます。

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
| `--rx-plugin-dir PATH` | VST3 ディレクトリ上書き | OSに応じて自動検出(下記) |

**OS別の RX VST3 デフォルト探索先** (自動判定):

| OS | 探索パス |
|---|---|
| Windows | `C:\Program Files\Common Files\VST3\iZotope\` |
| macOS | `/Library/Audio/Plug-Ins/VST3/iZotope/` (システム) と `~/Library/Audio/Plug-Ins/VST3/iZotope/` (ユーザー) を順に探索 |
| Linux | (iZotope非対応) |

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

#### マルチバンドEQ (常時有効、0 dB = 何もしない)

| パラメータ | 範囲 | 効果 |
|---|---|---|
| `--eq-low-shelf` | -6〜+6 dB | **Low shelf @120Hz**。低域全体の量感。+で太く/重く、-で軽く |
| `--eq-low-mid` | -6〜+6 dB | **Peak @400Hz**。こもり帯域。-で抜けが良くなる(-1〜-2が定番)、+でボディ感 |
| `--eq-high-mid` | -6〜+6 dB | **Peak @1.5kHz**。明瞭度・前傾度。+で前に出る、-でまろやか |
| `--eq-high-shelf` | -6〜+6 dB | **High shelf @8kHz**。空気感・煌めき。+でエアリーに、-で落ち着く |

#### コンプレッサー (`--comp` で有効化)

> **機能**: 大きい音だけを潰して全体の音量バランスを均一化。ボーカルに掛けると安定感が出てリバーブの掛かりも自然になる。

| パラメータ | 範囲 | 効果 |
|---|---|---|
| `--comp-threshold` | -40〜0 dB | 圧縮開始ライン。**-18 が定番**。低い(-25等)ほど深くかかる |
| `--comp-ratio` | 1〜10 | 圧縮比。2:1=軽い / **3:1=自然** / 4-6:1=しっかり / 8:1+=リミッター |
| `--comp-attack` | 0.1〜50 ms | 反応速度。**短い(1-3)=パツッ** / 長い(10-30)=アタック残す |
| `--comp-release` | 20〜500 ms | 解放速度。**50-150 がボーカル定番**。短いとパンプ感 |

#### ディエッサー (`--deess` で有効化)

> **機能**: 「サ・シ・ス」音の刺さりを抑える。指定周波数より上を抜き出してその帯域だけにコンプを掛けるクロスオーバー式。声の本体は変えない。

| パラメータ | 範囲 | 効果 |
|---|---|---|
| `--deess-freq` | 3000〜12000 Hz | サ行を狙う帯域。**日本語声で 5-8kHz、英語声で 6-9kHz** |
| `--deess-threshold` | -40〜0 dB | 抑制開始ライン。低いほど積極的に掛かる |
| `--deess-ratio` | 1〜10 | 圧縮比。**4:1 が定番**。8:1+ で完全除去寄り |

#### フォルマント / 男声・女声 補正

> **機能**: 声色のジェンダー方向の微調整。`--formant-shift` は単独でも使え、`--gender-shift` はピッチと組み合わせて動く。

| パラメータ | 範囲 | 効果 |
|---|---|---|
| `--formant-shift` | 0.80〜1.20 | フォルマント比。**1.0=変更なし** / 0.85=チェスティ男声寄り / 1.15=ブライト女声寄り。0.95-1.05 が自然な微調整 |
| `--gender-shift` | -1〜+1 | ピッチ+フォルマント同時シフト。**0=変更なし** / -1=深い男声(-3半音+formant 0.82) / +1=高い女声(+3半音+formant 1.18) |

#### 子音強調 / 抑制 (`--consonant`)

> **機能**: トランジェント検出(librosa onset)で子音アタックだけにゲインを掛ける。声の本体は変えない。

| パラメータ | 範囲 | 効果 |
|---|---|---|
| `--consonant` | -1〜+1 | **0=変更なし** / -1〜-0.3=ささやき・柔らかく / +0.3〜+1=歯切れ良く・ラップ向け |
| `--consonant-sens` | 0.1〜1.5 | 検出感度。**0.5=標準** / 1.0=強いピークのみ / 0.3=ゆるく |

#### 自動ブレス挿入 (`--breath` で有効化)

> **機能**: AI歌声最大の不自然さ「息継ぎが無い」を補う。無音区間を検出して合成ブレス音を差し込む。フレーズ間に隙間が無い素材では何も起きない。

| パラメータ | 範囲 | 効果 |
|---|---|---|
| `--breath-threshold` | -60〜-20 dB | 無音判定。**-40=標準** / -50=厳しく / -30=ゆるく |
| `--breath-min-silence` | 0.2〜2.0 秒 | この長さ以上の無音だけにブレスを入れる。**0.4=標準** |
| `--breath-intensity` | 0〜0.2 | ブレス音量。**0.05=自然** / 0.03=ささやかな息 / 0.1+=はっきり聞こえる |

#### コーラス・ダブラー (`--chorus` で有効化)

> **機能**: 声を「もう一人/数人で歌っている風」に厚くするモジュレーション系。設定次第でダブラー(自然な厚み)からコーラス(分厚い合唱)まで。

| パラメータ | 範囲 | 効果 |
|---|---|---|
| `--chorus-rate` | 0.1〜5 Hz | 揺らぎ速度。**0.3-0.7=ダブラー風** / 1-2=軽コーラス / 3+=ロータリー寄り |
| `--chorus-depth` | 0〜1 | 揺らぎ深さ。**0.1=ほぼダブラー** / 0.25=自然 / 0.5+=分厚い |
| `--chorus-mix` | 0〜1 | エフェクト混ぜ率。**0.2=控えめ** / 0.4=半々 / 0.6+=主体 |

## ファイル構成

```
vo_fix/
├── humanize.py        # pyworld f0 jitter + amp shimmer + formant + gender
├── vocal_processing.py# 子音強調・抑制 + 自動ブレス挿入
├── effects.py         # 4バンドEQ + コンプ + ディエッサー + コーラス + EQ/saturation/reverb
├── vst.py             # iZotope RX VST3 ローダー (OS自動判別)
├── pipeline.py        # オーケストレーション + プリセット
├── user_presets.py    # マイプリセット保存/読み込み
├── operation_log.py   # 操作ログ
├── theme.py           # Spotify風 Gradio テーマ
├── io.py              # wav 読み書き
├── rvc.py             # スタブ (Applio 連携を推奨)
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

## ステム合成 / 最終ミックス

インストゥルメンタルや STEM (ドラム / ベース等) を一緒に渡せば、加工済みボーカルと **合成して1曲として書き出し** ます。SUNO で別々に書き出した vocal stem と instrumental stem を直接合体させて完成形まで持っていけます。

### Gradio で

「ステム合成 / 最終ミックス」アコーディオンを開いて:

1. **ステム / インストゥルメンタル**: wav/flac/mp3 を複数選択(ドラッグ&ドロップOK)
2. **ボーカル / ステム / マスター ゲイン** を調整
3. 変換ボタン → 加工済みボーカル + ステム合成 → 1ファイル出力

### CLI で

```powershell
.\.venv\Scripts\python.exe cli.py `
  -i vocal.wav `
  -o final_song.wav `
  --preset natural `
  --stem instrumental.wav `
  --stem drums.wav `
  --stem bass.wav `
  --vocal-gain 0 `
  --stems-gain -3 `
  --master-gain -1
```

### 動作仕様

| | 内容 |
|---|---|
| 加工対象 | 「入力 (wav)」のボーカルのみ。ステムは **そのまま** ミックス |
| サンプルレート | ボーカルに合わせて自動リサンプル |
| チャンネル | mono ボーカル × stereo ステム等もすべて自動対応 |
| 長さ | 最も長いトラックに合わせる(イントロ/アウトロのインストが残る)、足りない箇所は無音パディング |
| クリップ防止 | peak > 0.99 で自動正規化 |

## 出力品質(サンプルレート / ビット深度 / チャンネル)

**デフォルトは入力品質をそのまま保持** します。24-bit/48kHz の **ステレオ** 素材を読ませれば 24-bit/48kHz の **ステレオ** で出力されます。

| 設定 | 動作 |
|---|---|
| デフォルト | 入力 sample rate / bit depth / **チャンネル数** をすべて保持 |
| `--target-sr 48000` | 強制リサンプル(必要なら 44100 / 88200 / 96000 等) |
| `--output-subtype PCM_24` | 24-bit PCM で書き出し |
| `--output-subtype FLOAT` | **32-bit float で書き出し**(最高精度、DAW持ち込み向け) |
| `--output-subtype PCM_16` | 16-bit PCM (CD品質、サイズ重視) |
| `--mono` | ステレオ入力をモノラルに集約して処理(処理時間 半減、ステレオ幅は失う) |

### ステレオ処理について

ステレオ入力は **L/R 独立して同じパイプラインを通す** ことで処理されます。シード値を共有することで、両チャンネルが「同じ歌い方の揺らぎ」になり、定位がブレません。

処理時間がモノラル比で約2倍になるので、急ぐ場合は `--mono` または Gradio UI の「ステレオ→モノラルに集約」チェックでスピード優先にできます。

**過去のユーザープリセットに 44100 が記録されている場合**: `~/.vo_fix/presets/<name>.json` を開いて `target_sr` を `null` に書き換えると入力保持に戻せます。

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
| `UnicodeDecodeError: 'cp932' codec can't decode...` | pip が古い (22.x) のが原因。`python -m pip install --upgrade pip` を実行してから retry |
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
