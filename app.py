"""Gradio UI for vo_fix.

Run: python app.py
Opens http://localhost:7860
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import gradio as gr
import numpy as np
import soundfile as sf

from vo_fix.effects import EffectsConfig
from vo_fix.humanize import HumanizeConfig
from vo_fix.io import SUBTYPE_LABELS, load_wav, save_wav
from vo_fix.mix import MixConfig, mix_with_stems
from vo_fix.operation_log import OperationLog
from vo_fix.pipeline import PRESETS, ProcessConfig, RXConfig, process_array
from vo_fix.theme import CUSTOM_CSS, build_theme
from vo_fix.user_presets import (
    all_preset_names,
    delete_user_preset,
    export_all_presets,
    get_presets_dir,
    import_presets,
    list_user_presets,
    resolve_preset,
    save_user_preset,
)
from vo_fix.vocal_processing import VocalProcessingConfig
from vo_fix.vst import DEFAULT_RX_DIR, DEFAULT_RX_DIRS, find_rx_plugins

# Single shared log for the running app instance. Gradio is single-process
# so we don't need locking — but multiple browser tabs share state, which
# is the right behavior here ("activity feed for this vo_fix instance").
OP_LOG = OperationLog()


# Ordered field names for the param payload. Defined once so the UI input
# list and the runner can stay in sync.
PARAM_FIELDS = [
    # humanize
    "jitter_cents", "vibrato_depth", "vibrato_rate", "shimmer",
    # base effects
    "high_cut", "presence_db", "saturation", "reverb_mix", "reverb_room",
    # skip toggles + mono
    "skip_humanize", "skip_effects", "force_mono",
    # RX
    "rx_denoise_on", "rx_denoise_db", "rx_declick_on", "rx_declick_sens", "rx_plugin_dir",
    # multi-band EQ
    "eq_low_shelf", "eq_low_mid", "eq_high_mid", "eq_high_shelf",
    # compressor
    "comp_on", "comp_threshold", "comp_ratio", "comp_attack", "comp_release",
    # de-esser
    "deess_on", "deess_freq", "deess_threshold", "deess_ratio",
    # chorus
    "chorus_on", "chorus_rate", "chorus_depth", "chorus_mix",
    # vocal: formant + gender
    "formant_shift", "gender_shift",
    # vocal: consonant
    "consonant_amount", "consonant_sens",
    # vocal: breath
    "breath_on", "breath_threshold", "breath_min_silence", "breath_intensity",
    # output quality
    "output_sr_choice", "output_subtype_choice",
]

# Sample rate dropdown options. "preserve" maps to None in ProcessConfig.
SR_CHOICES = ["入力を保持", "44100", "48000", "88200", "96000"]
# Bit depth dropdown options.
SUBTYPE_CHOICES = ["入力を保持"] + list(SUBTYPE_LABELS.keys())


def _sr_choice_to_value(choice: str) -> int | None:
    if choice == "入力を保持" or not choice:
        return None
    return int(choice)


def _subtype_choice_to_value(choice: str) -> str | None:
    if choice == "入力を保持" or not choice:
        return None
    return choice


def _value_to_sr_choice(v: int | None) -> str:
    if v is None:
        return "入力を保持"
    return str(v)


def _value_to_subtype_choice(v: str | None) -> str:
    if v is None:
        return "入力を保持"
    return v


def _params_to_config(preset_name: str, params: dict) -> tuple[ProcessConfig, ProcessConfig]:
    """Build (base_preset_config, current_config_with_overrides) from a dict."""
    base = resolve_preset(preset_name)
    current = ProcessConfig(
        humanize=HumanizeConfig(
            jitter_cents=float(params["jitter_cents"]),
            vibrato_depth_cents=float(params["vibrato_depth"]),
            vibrato_rate_hz=float(params["vibrato_rate"]),
            shimmer=float(params["shimmer"]),
            jitter_rate_hz=base.humanize.jitter_rate_hz,
            shimmer_rate_hz=base.humanize.shimmer_rate_hz,
            formant_shift_ratio=float(params["formant_shift"]),
            gender_shift=float(params["gender_shift"]),
        ),
        vocal=VocalProcessingConfig(
            consonant_amount=float(params["consonant_amount"]),
            consonant_sensitivity=float(params["consonant_sens"]),
            breath_enabled=bool(params["breath_on"]),
            breath_threshold_db=float(params["breath_threshold"]),
            breath_min_silence_s=float(params["breath_min_silence"]),
            breath_intensity=float(params["breath_intensity"]),
        ),
        effects=EffectsConfig(
            high_cut_hz=float(params["high_cut"]),
            presence_db=float(params["presence_db"]),
            saturation=float(params["saturation"]),
            reverb_mix=float(params["reverb_mix"]),
            reverb_room=float(params["reverb_room"]),
            # EQ
            eq_low_shelf_db=float(params["eq_low_shelf"]),
            eq_low_mid_db=float(params["eq_low_mid"]),
            eq_high_mid_db=float(params["eq_high_mid"]),
            eq_high_shelf_db=float(params["eq_high_shelf"]),
            # Compressor
            compressor_enabled=bool(params["comp_on"]),
            compressor_threshold_db=float(params["comp_threshold"]),
            compressor_ratio=float(params["comp_ratio"]),
            compressor_attack_ms=float(params["comp_attack"]),
            compressor_release_ms=float(params["comp_release"]),
            # De-esser
            deesser_enabled=bool(params["deess_on"]),
            deesser_freq_hz=float(params["deess_freq"]),
            deesser_threshold_db=float(params["deess_threshold"]),
            deesser_ratio=float(params["deess_ratio"]),
            # Chorus
            chorus_enabled=bool(params["chorus_on"]),
            chorus_rate_hz=float(params["chorus_rate"]),
            chorus_depth=float(params["chorus_depth"]),
            chorus_mix=float(params["chorus_mix"]),
        ),
        rx=RXConfig(
            voice_denoise_enabled=bool(params["rx_denoise_on"]),
            voice_denoise_reduction_db=float(params["rx_denoise_db"]),
            declick_enabled=bool(params["rx_declick_on"]),
            declick_sensitivity=float(params["rx_declick_sens"]),
            plugin_dir=params["rx_plugin_dir"] or None,
        ),
        target_sr=_sr_choice_to_value(params["output_sr_choice"]),
        output_subtype=_subtype_choice_to_value(params["output_subtype_choice"]),
        skip_humanize=bool(params["skip_humanize"]),
        skip_effects=bool(params["skip_effects"]),
        force_mono=bool(params["force_mono"]),
    )
    return base, current


def _config_to_param_values(p: ProcessConfig) -> list:
    """Pull current config values back into the slider value order (PARAM_FIELDS).

    Used to populate the UI when a preset is selected. Order MUST match
    PARAM_FIELDS exactly.
    """
    return [
        p.humanize.jitter_cents,
        p.humanize.vibrato_depth_cents,
        p.humanize.vibrato_rate_hz,
        p.humanize.shimmer,
        p.effects.high_cut_hz,
        p.effects.presence_db,
        p.effects.saturation,
        p.effects.reverb_mix,
        p.effects.reverb_room,
        p.skip_humanize,
        p.skip_effects,
        p.force_mono,
        p.rx.voice_denoise_enabled,
        p.rx.voice_denoise_reduction_db,
        p.rx.declick_enabled,
        p.rx.declick_sensitivity,
        p.rx.plugin_dir or "",
        p.effects.eq_low_shelf_db,
        p.effects.eq_low_mid_db,
        p.effects.eq_high_mid_db,
        p.effects.eq_high_shelf_db,
        p.effects.compressor_enabled,
        p.effects.compressor_threshold_db,
        p.effects.compressor_ratio,
        p.effects.compressor_attack_ms,
        p.effects.compressor_release_ms,
        p.effects.deesser_enabled,
        p.effects.deesser_freq_hz,
        p.effects.deesser_threshold_db,
        p.effects.deesser_ratio,
        p.effects.chorus_enabled,
        p.effects.chorus_rate_hz,
        p.effects.chorus_depth,
        p.effects.chorus_mix,
        p.humanize.formant_shift_ratio,
        p.humanize.gender_shift,
        p.vocal.consonant_amount,
        p.vocal.consonant_sensitivity,
        p.vocal.breath_enabled,
        p.vocal.breath_threshold_db,
        p.vocal.breath_min_silence_s,
        p.vocal.breath_intensity,
        _value_to_sr_choice(p.target_sr),
        _value_to_subtype_choice(p.output_subtype),
    ]


def run(
    audio_path,
    preset,
    *param_values,
    rvc_model_path="",
    rvc_index_path="",
    rvc_pitch=0.0,
    stem_files=None,
    vocal_gain=0.0,
    stems_gain=0.0,
    master_gain=0.0,
):
    if audio_path is None:
        return None, "音声ファイルをアップロードしてください", OP_LOG.as_text()

    if len(param_values) < len(PARAM_FIELDS):
        return None, f"内部エラー: パラメータ数 {len(param_values)} (期待 {len(PARAM_FIELDS)})", OP_LOG.as_text()

    params = dict(zip(PARAM_FIELDS, param_values))
    base, cfg = _params_to_config(preset, params)
    if rvc_model_path:
        cfg.rvc_model_path = rvc_model_path
        cfg.rvc_index_path = rvc_index_path or None
        cfg.rvc_pitch_semitones = float(rvc_pitch)

    # Stem mixing
    stem_paths = [s for s in (stem_files or []) if s]
    if stem_paths:
        cfg.mix.enabled = True
        cfg.mix.stem_paths = stem_paths
        cfg.mix.vocal_gain_db = float(vocal_gain)
        cfg.mix.stems_gain_db = float(stems_gain)
        cfg.mix.master_gain_db = float(master_gain)

    t0 = time.perf_counter()
    try:
        samples, sr, meta = load_wav(
            audio_path, target_sr=cfg.target_sr, force_mono=cfg.force_mono
        )
        out, out_sr = process_array(samples, sr, cfg)
        # Final stage: mix in stems if any were provided
        out = mix_with_stems(out, out_sr, cfg.mix)
        out_path = Path(tempfile.mkdtemp()) / "vo_fix_out.wav"
        used_subtype = save_wav(
            out_path,
            out,
            out_sr,
            subtype=cfg.output_subtype,
            input_subtype=meta.subtype,
        )
        elapsed = time.perf_counter() - t0
        OP_LOG.record_run(
            preset_name=preset,
            preset_config=base,
            actual_config=cfg,
            input_path=audio_path,
            output_path=str(out_path),
            duration_seconds=elapsed,
        )
        status_msg = (
            f"完了 — {len(out)/out_sr:.2f}s @ {out_sr}Hz / {used_subtype}"
            f"  (入力: {meta.sample_rate}Hz / {meta.subtype}, 処理 {elapsed:.2f}s)"
        )
        return str(out_path), status_msg, OP_LOG.as_text()
    except Exception as e:
        return None, f"エラー: {e}", OP_LOG.as_text()


def run_wrapper(*args):
    """Gradio passes positional args. Order:
    audio_path, preset, *PARAM_FIELDS, rvc_model, rvc_index, rvc_pitch,
    stem_files, vocal_gain, stems_gain, master_gain
    """
    audio_path, preset = args[0], args[1]
    n_params = len(PARAM_FIELDS)
    param_values = args[2 : 2 + n_params]
    rest = args[2 + n_params :]
    rvc_model, rvc_index, rvc_pitch = rest[0], rest[1], rest[2]
    stem_files, vocal_gain, stems_gain, master_gain = rest[3], rest[4], rest[5], rest[6]
    return run(
        audio_path, preset, *param_values,
        rvc_model_path=rvc_model,
        rvc_index_path=rvc_index,
        rvc_pitch=rvc_pitch,
        stem_files=stem_files,
        vocal_gain=vocal_gain,
        stems_gain=stems_gain,
        master_gain=master_gain,
    )


def load_preset_values(preset_name):
    p = resolve_preset(preset_name)
    return _config_to_param_values(p)


def save_current_as_preset(new_name, preset, *param_values):
    new_name = (new_name or "").strip()
    if not new_name:
        return gr.update(), "⚠️ プリセット名を入力してください"
    params = dict(zip(PARAM_FIELDS, param_values))
    _, cfg = _params_to_config(preset, params)
    try:
        path = save_user_preset(new_name, cfg)
        choices = all_preset_names()
        return (
            gr.update(choices=choices, value=f"user: {new_name}"),
            f"✅ 保存しました: {path.name}",
        )
    except Exception as e:
        return gr.update(), f"❌ 保存失敗: {e}"


def delete_current_preset(preset):
    if not preset.startswith("user: "):
        return gr.update(), "⚠️ 組み込みプリセットは削除できません"
    name = preset[len("user: ") :]
    deleted = delete_user_preset(name)
    choices = all_preset_names()
    if deleted:
        return gr.update(choices=choices, value="natural"), f"🗑 削除しました: {name}"
    return gr.update(choices=choices), f"⚠️ 見つかりませんでした: {name}"


def clear_log():
    OP_LOG.clear()
    return OP_LOG.as_text()


def export_presets_action():
    """Bundle every saved preset into a downloadable zip."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = Path(tempfile.mkdtemp()) / f"vo_fix_presets_{stamp}.zip"
    export_all_presets(out)
    count = len(list_user_presets())
    msg = f"✅ {count} 件のプリセットをエクスポートしました ({out.name})"
    return str(out), msg


def import_presets_action(zip_file_path, overwrite_flag):
    """Restore presets from an uploaded zip."""
    if not zip_file_path:
        return gr.update(), "⚠️ zip ファイルを選択してください"
    try:
        imported, skipped = import_presets(zip_file_path, overwrite=bool(overwrite_flag))
        choices = all_preset_names()
        msg = (
            f"✅ {imported} 件をインポート"
            + (f", {skipped} 件は既存のためスキップ" if skipped else "")
            + (" (上書きON)" if overwrite_flag else "")
        )
        return gr.update(choices=choices), msg
    except Exception as e:
        return gr.update(), f"❌ インポート失敗: {e}"


def build_ui():
    with gr.Blocks(title="vo_fix — AI歌声ナチュラライザー") as demo:
        gr.HTML(
            '<div class="vo-fix-brand">'
            "<h1>vo_fix — AI歌声ナチュラライザー</h1>"
            "<p>SUNO等のAI歌声に揺らぎとミックス処理を足して人間っぽくします。</p>"
            "</div>"
        )

        with gr.Row():
            with gr.Column():
                audio_in = gr.Audio(label="入力 (wav)", type="filepath")
                preset = gr.Dropdown(
                    choices=all_preset_names(),
                    value="natural",
                    label="プリセット",
                    info="出発点。下のスライダーを動かすと上書きされる。`user:` が付くものはあなたの保存したカスタム",
                )
                gr.Markdown(
                    "**プリセットの使い分け**  \n"
                    "🔘 **off** — 何もしない(処理前との比較用)  \n"
                    "🟢 **natural** — 自然な揺らぎ + 軽いミックス。迷ったらコレ  \n"
                    "💜 **intimate** — 揺らぎ強め + リバーブ深め。バラード・ささやき・しっとり系  \n"
                    "💡 **polished** — 揺らぎ控えめ + 高域明るめ + リバーブ薄め。前に出したいポップス向け"
                )

                with gr.Accordion("マイプリセット (保存・削除・バックアップ)", open=False):
                    presets_path = str(get_presets_dir())
                    gr.Markdown(
                        "_現在のスライダー値に名前を付けて保存。次回起動時にもプリセット一覧に出ます。_  \n"
                        f"📂 **保存先**: `{presets_path}`  \n"
                        "_この場所はプロジェクトフォルダの外なので、`git pull` でも消えません。_  \n"
                        "_万が一に備えて zip エクスポートでバックアップを取っておくと安心です。_"
                    )
                    new_preset_name = gr.Textbox(
                        label="保存名",
                        placeholder="例: my-ballad / suno-pop-vibe",
                        info="保存ボタンで現在のスライダー全部を記録",
                    )
                    with gr.Row():
                        save_btn = gr.Button("💾 現在の設定を保存", variant="secondary")
                        delete_btn = gr.Button("🗑 選択中のuser:を削除", variant="secondary")
                    preset_status = gr.Textbox(label="プリセット操作結果", interactive=False)

                    gr.Markdown("---")
                    gr.Markdown("**バックアップ / 復元**")
                    with gr.Row():
                        export_btn = gr.Button("📦 全プリセットを zip でエクスポート", variant="secondary")
                    export_file = gr.File(label="エクスポートされた zip", interactive=False)
                    import_file = gr.File(
                        label="インポートする zip(ドラッグ&ドロップ可)",
                        file_count="single",
                        type="filepath",
                        file_types=[".zip"],
                    )
                    import_overwrite = gr.Checkbox(
                        label="既存と同名なら上書き", value=False,
                        info="OFFなら同名はスキップ。ONなら zip 内容で置き換え"
                    )
                    import_btn = gr.Button("📥 zip からインポート", variant="secondary")

                with gr.Accordion("揺らぎ (Humanize)", open=True):
                    gr.Markdown("_AI歌声の「均一すぎる」ピッチと音量に、人間の声の有機的な揺れを加える段。_")
                    jitter_cents = gr.Slider(
                        0, 30, value=8, step=0.5,
                        label="ピッチ jitter (cents)",
                        info="ピッチの微小な揺れ幅。0=AIそのまま / 8=自然 / 15+=酔った歌い手。100cents=半音",
                    )
                    vibrato_depth = gr.Slider(
                        0, 30, value=0, step=0.5,
                        label="ビブラート深さ (cents)",
                        info="曲全体に乗せるビブラートの深さ。0=既存だけ揺らす / 3-8=自然 / 15+=演歌・オペラ寄り",
                    )
                    vibrato_rate = gr.Slider(
                        3, 8, value=5.5, step=0.1,
                        label="ビブラート速度 (Hz)",
                        info="ビブラートが揺れる速さ。人間は 5-6 Hz が自然。7+ で神経質、4 でゆったり",
                    )
                    shimmer = gr.Slider(
                        0, 0.1, value=0.03, step=0.005,
                        label="アンプ shimmer",
                        info="音量の細かい揺れ。0=平坦(機械的) / 0.03=自然な息づかい / 0.08+=不安定で生々しい",
                    )
                    skip_humanize = gr.Checkbox(
                        label="揺らぎをスキップ",
                        value=False,
                        info="チェックすると揺らぎ処理を完全に飛ばす(エフェクトだけ掛けたい時用)",
                    )

                with gr.Accordion("エフェクト (基本)", open=True):
                    gr.Markdown("_pedalboard による EQ・歪み・空間系。ミックス的な仕上げ。_")
                    high_cut = gr.Slider(
                        4000, 18000, value=9000, step=100,
                        label="ハイカット (Hz)",
                        info="ここより上の高域を削る。AI特有のシャリつき抑制。低いほど暗く落ち着く。8000-10000 が目安",
                    )
                    presence_db = gr.Slider(
                        -6, 6, value=0.5, step=0.1,
                        label="プレゼンス @3kHz (dB)",
                        info="3kHz 付近(声の明瞭度帯)のブースト。+で前に出る/明瞭 / -で奥に引っ込む/まろやか",
                    )
                    saturation = gr.Slider(
                        0, 1, value=0.15, step=0.01,
                        label="サチュレーション",
                        info="アナログテープ風の倍音歪み。0=デジタルクリア / 0.15=温かみ / 0.4+=ロック・ローファイ寄り",
                    )
                    reverb_mix = gr.Slider(
                        0, 1, value=0.08, step=0.01,
                        label="リバーブ wet",
                        info="空間の響き量。0=密室(ドライ) / 0.1=普通の部屋 / 0.3+=お風呂・ホール感",
                    )
                    reverb_room = gr.Slider(
                        0, 1, value=0.35, step=0.01,
                        label="リバーブ room",
                        info="響く部屋の大きさ。0=小箱(短い残響) / 0.5=居室 / 1=大ホール(長い余韻)",
                    )
                    skip_effects = gr.Checkbox(
                        label="エフェクトをスキップ",
                        value=False,
                        info="チェックするとエフェクト段すべて(EQ/コンプ/サチュ/リバーブ等)を飛ばす",
                    )

                with gr.Accordion("詳細エフェクト: 4バンド EQ", open=False):
                    gr.Markdown(
                        "### 機能説明: マルチバンド・イコライザー\n"
                        "声を 4 つの帯域に分けて音色を調整します。"
                        "**ボーカルミックスの基本** で、不要な帯域を削ったり魅力的な帯域を強調することで「抜け」「太さ」「明るさ」を整えます。\n"
                        "- 全部 0 dB なら何もしないので有効/無効スイッチは不要"
                    )
                    eq_low_shelf = gr.Slider(
                        -6, 6, value=0, step=0.5,
                        label="Low shelf @120Hz (dB)",
                        info="低域の量感。+で太く重く / -で軽く前に。AI声に1-2dB足すと立体感が出やすい",
                    )
                    eq_low_mid = gr.Slider(
                        -6, 6, value=0, step=0.5,
                        label="Peak @400Hz (dB)",
                        info="こもり帯域。-で抜けが良くなり / +でボディ感。普通は -1〜-2 で抜けを稼ぐ",
                    )
                    eq_high_mid = gr.Slider(
                        -6, 6, value=0, step=0.5,
                        label="Peak @1.5kHz (dB)",
                        info="明瞭度・前傾度。+で前に出る / -でまろやか。1-2dB ブーストでクリアになる",
                    )
                    eq_high_shelf = gr.Slider(
                        -6, 6, value=0, step=0.5,
                        label="High shelf @8kHz (dB)",
                        info="空気感・煌めき。+でエアリーに / -で落ち着いた音。プレゼンスとは別の高域",
                    )

                with gr.Accordion("詳細エフェクト: コンプレッサー", open=False):
                    gr.Markdown(
                        "### 機能説明: コンプレッサー\n"
                        "**大きい音だけを潰して全体の音量バランスを均一化** するエフェクト。"
                        "AI歌声は音量がフラットですが、それでも長尺曲ではダイナミクスがブレることがあります。"
                        "コンプを軽く掛けると安定感が出て、リバーブの掛かりも自然になります。\n"
                        "- 副作用としてサスティーンが伸びるので、息感も保ちたい時は弱めに(2:1 程度)"
                    )
                    comp_on = gr.Checkbox(
                        label="コンプレッサーを使う",
                        value=False,
                        info="チェックして下のパラメータで動作開始",
                    )
                    comp_threshold = gr.Slider(
                        -40, 0, value=-18, step=0.5,
                        label="閾値 threshold (dB)",
                        info="この音量を超えた部分が圧縮対象。-18dB はボーカル定番。低い(-25等)ほど深くかかる",
                    )
                    comp_ratio = gr.Slider(
                        1, 10, value=3, step=0.5,
                        label="比率 ratio",
                        info="2:1=軽い / 3:1=自然なボーカル / 4-6:1=しっかり / 8:1+=リミッター寄り",
                    )
                    comp_attack = gr.Slider(
                        0.1, 50, value=5, step=0.1,
                        label="アタック attack (ms)",
                        info="反応の速さ。短い(1-3ms)=パツッとした音 / 長い(10-30ms)=自然・アタック残す",
                    )
                    comp_release = gr.Slider(
                        20, 500, value=80, step=10,
                        label="リリース release (ms)",
                        info="圧縮が抜ける速さ。短いとパンプ感、長いと滑らか。50-150ms がボーカル標準",
                    )

                with gr.Accordion("詳細エフェクト: ディエッサー", open=False):
                    gr.Markdown(
                        "### 機能説明: ディエッサー\n"
                        "**「サ・シ・ス」音の刺さりを抑える** 専用処理。"
                        "AI歌声は子音の制御が苦手で、サ行が突き刺さってヘッドホンで聴くと耳が痛いことがあります。\n\n"
                        "**仕組み**: 6-8kHz 付近だけを取り出してその帯域だけにコンプを掛け、サ行のピークだけを抑える(クロスオーバー式)。"
                        "コンプとは別物で、声の本体には影響しません。"
                    )
                    deess_on = gr.Checkbox(
                        label="ディエッサーを使う",
                        value=False,
                        info="サ行が刺さる時だけ ON。問題ない素材なら OFF のまま",
                    )
                    deess_freq = gr.Slider(
                        3000, 12000, value=6500, step=100,
                        label="周波数 (Hz)",
                        info="どの帯域のサ行を狙うか。日本語声で 5-8kHz、英語声で 6-9kHz 目安",
                    )
                    deess_threshold = gr.Slider(
                        -40, 0, value=-25, step=0.5,
                        label="閾値 (dB)",
                        info="この帯域のエネルギーがこの値を超えたら抑制。低いほど積極的に掛かる",
                    )
                    deess_ratio = gr.Slider(
                        1, 10, value=4, step=0.5,
                        label="比率",
                        info="4:1 が定番。8:1 まで上げるとほぼリミッターで刺さりを完全除去",
                    )

                with gr.Accordion("音処理: フォルマント微変調", open=False):
                    gr.Markdown(
                        "### 機能説明: フォルマント微変調\n"
                        "**声の質感そのもの** を微調整します。フォルマントは声道の共鳴ピークで、声の「太さ・細さ・明るさ」を決める正体です。\n\n"
                        "- ピッチは変えずにフォルマントだけ動かすので、**メロディはそのままで声色だけ変わる**\n"
                        "- 1.0 = 無変更 / <1.0 = チェスティで太い男声寄り / >1.0 = ブライトで女声寄り\n"
                        "- 0.95-1.05 の微変調が「不自然にならず印象を変える」スイートスポット"
                    )
                    formant_shift = gr.Slider(
                        0.80, 1.20, value=1.0, step=0.01,
                        label="フォルマント比 (1.0=neutral)",
                        info="0.85 = 重厚な男声化 / 0.95 = 少し低めに / 1.05 = 少し高めに / 1.15 = 明るく女声化",
                    )

                with gr.Accordion("音処理: 男声 ⇔ 女声 補正", open=False):
                    gr.Markdown(
                        "### 機能説明: 男声 ⇔ 女声 補正\n"
                        "**ピッチとフォルマントを同時に動かす** ジェンダー方向の補正スライダー。"
                        "ピッチだけ上げると「ヘリウム声」、フォルマントだけ上げると「ミッキー声」になりますが、両方適切に動かすと自然な性別変換になります。\n\n"
                        "- 0 = 無変更\n"
                        "- 負方向: ピッチ↓ + フォルマント↓ = 男声化\n"
                        "- 正方向: ピッチ↑ + フォルマント↑ = 女声化\n"
                        "- フォルマント微変調 と同時指定で乗算合成されます"
                    )
                    gender_shift = gr.Slider(
                        -1.0, 1.0, value=0.0, step=0.05,
                        label="性別シフト",
                        info="-1.0 = 深い男声(-3半音+formant 0.82) / 0 = 元のまま / +1.0 = 高い女声(+3半音+formant 1.18)",
                    )

                with gr.Accordion("音処理: 子音強調 / 抑制", open=False):
                    gr.Markdown(
                        "### 機能説明: 子音強調・抑制\n"
                        "**「歯切れ」を調整する** トランジェント処理。子音のアタック部分だけを検出してゲインを変えます。\n\n"
                        "- **+方向(強調)**: 滑舌が良くなる、前に出る、ラップやポップス向き\n"
                        "- **-方向(抑制)**: 柔らかく、ささやき声っぽく、バラード・ASMR 向き\n"
                        "- 仕組み: librosa の onset 検出 + ゲインエンベロープ。声の本体には影響しない"
                    )
                    consonant_amount = gr.Slider(
                        -1.0, 1.0, value=0.0, step=0.05,
                        label="子音調整量",
                        info="-1 = 大きく抑制 / -0.3 = 柔らかく / 0 = 無変更 / +0.3 = 歯切れ良く / +1 = 強調",
                    )
                    consonant_sens = gr.Slider(
                        0.1, 1.5, value=0.5, step=0.05,
                        label="検出感度",
                        info="高いほど強いトランジェントだけ反応。0.3=ゆるく全体的、1.0=ピークのみ",
                    )

                with gr.Accordion("音処理: 自動ブレス挿入", open=False):
                    gr.Markdown(
                        "### 機能説明: 自動ブレス挿入\n"
                        "**長い無音区間に合成ブレス(息継ぎ音)を差し込む** 機能です。"
                        "AI歌声の最大の不自然さの一つは「息継ぎが無いこと」。"
                        "音楽的なフレーズの隙間にブレスを足すと一気に人間味が出ます。\n\n"
                        "- 仕組み: RMS で無音区間を検出 → 帯域制限ノイズ + ASR エンベロープでブレス合成 → 隙間中央にクロスフェード挿入\n"
                        "- **音楽が止まっている区間が無い場合は何も起きません**(意図的なフレーズ間にだけ入る)"
                    )
                    breath_on = gr.Checkbox(
                        label="ブレス挿入を有効化",
                        value=False,
                        info="チェックするとフレーズの隙間に息継ぎが差し込まれる",
                    )
                    breath_threshold = gr.Slider(
                        -60, -20, value=-40, step=1,
                        label="無音判定 (dB)",
                        info="この値より静かな区間を無音と判定。-40=普通 / -50=厳しめ / -30=ゆるく",
                    )
                    breath_min_silence = gr.Slider(
                        0.2, 2.0, value=0.4, step=0.1,
                        label="最小無音長 (秒)",
                        info="この長さ以上の無音だけにブレスを入れる。短い隙間は無視",
                    )
                    breath_intensity = gr.Slider(
                        0.0, 0.2, value=0.05, step=0.005,
                        label="ブレス音量",
                        info="0.03 = ささやかな息 / 0.05 = 自然 / 0.1+ = はっきり聞こえる",
                    )

                with gr.Accordion("詳細エフェクト: コーラス・ダブラー", open=False):
                    gr.Markdown(
                        "### 機能説明: コーラス・ダブラー\n"
                        "**声を「もう一人/数人で歌っている風」に厚くする** モジュレーション系エフェクト。\n\n"
                        "- **ダブラー方向** (depth低・rate低・mix低): 同じ声がわずかにずれて重なる、自然な厚み\n"
                        "- **コーラス方向** (depth高・rate高・mix高): 複数人の合唱風、80年代ポップスっぽい揺らぎ\n\n"
                        "AI歌声に薄く掛けると「単声感」が減って人間っぽくなる効果も期待できます。"
                    )
                    chorus_on = gr.Checkbox(
                        label="コーラス・ダブラーを使う",
                        value=False,
                    )
                    chorus_rate = gr.Slider(
                        0.1, 5, value=0.8, step=0.1,
                        label="揺らぎ速度 rate (Hz)",
                        info="0.3-0.7 = ダブラー風(ほぼ静止) / 1-2 = 軽いコーラス / 3+ = ロータリー寄り",
                    )
                    chorus_depth = gr.Slider(
                        0, 1, value=0.25, step=0.05,
                        label="揺らぎ深さ depth",
                        info="0.1 = ほぼダブラー / 0.25 = 自然 / 0.5+ = 分厚いコーラス",
                    )
                    chorus_mix = gr.Slider(
                        0, 1, value=0.3, step=0.05,
                        label="ミックス量 mix",
                        info="エフェクト音の混ぜ率。0.2 = 控えめ / 0.4 = 半々 / 0.6+ = エフェクト主体",
                    )

                with gr.Accordion("iZotope RX 前処理 (オプション)", open=False):
                    rx_found = find_rx_plugins()
                    if rx_found:
                        gr.Markdown(f"✅ 検出: {', '.join(rx_found.keys())}")
                    else:
                        searched = "\n".join(f"- `{p}`" for p in DEFAULT_RX_DIRS)
                        gr.Markdown(
                            "⚠️ RX VST3 が見つかりません。以下の標準パスを探索:\n"
                            f"{searched}\n\n"
                            "別の場所にインストールしている場合は下のパス欄で指定してください。"
                        )
                    gr.Markdown(
                        "_素材を綺麗にしてから揺らぎを足す前処理段。**必ず humanize より前** に走ります。_"
                    )
                    rx_denoise_on = gr.Checkbox(
                        label="Voice De-noise を使う",
                        value=False,
                        info="SUNO 出力に乗る薄い広域ノイズ・ザラつきを除去。揺らぎ注入前のクリーンアップ",
                    )
                    rx_denoise_db = gr.Slider(
                        0, 20, value=6, step=0.5,
                        label="De-noise reduction (dB)",
                        info="ノイズ削減量。4-6=軽い / 8-10=しっかり / 15+=声まで削れて不自然になりがち",
                    )
                    rx_declick_on = gr.Checkbox(
                        label="De-click を使う",
                        value=False,
                        info="AI特有のデジタル子音アタックや微小クリック音を除去",
                    )
                    rx_declick_sens = gr.Slider(
                        0.5, 10, value=3, step=0.1,
                        label="De-click sensitivity",
                        info="検出感度。2-3=控えめ / 4-5=標準 / 7+=やり過ぎ(子音まで丸まる)",
                    )
                    default_paths_str = " / ".join(str(p) for p in DEFAULT_RX_DIRS)
                    rx_plugin_dir = gr.Textbox(
                        label="VST3 ディレクトリ (空欄でデフォルト)", value="",
                        info=f"OS別デフォルト: {default_paths_str}",
                    )

                with gr.Accordion("出力品質 (サンプルレート / ビット深度)", open=False):
                    gr.Markdown(
                        "### 機能説明: 出力品質\n"
                        "**入力ファイルの品質をそのまま保持** するのがデフォルト。"
                        "24-bit/48kHz の素材を読ませれば 24-bit/48kHz で出ます。"
                        "16-bit/44.1kHz への自動変換は **しません**。\n\n"
                        "- **サンプルレート保持**: 「入力を保持」のままにしておく(推奨)\n"
                        "- **ビット深度保持**: 同上。32-bit float を選べばさらに高精度で書き出せる"
                    )
                    output_sr_choice = gr.Dropdown(
                        choices=SR_CHOICES,
                        value="入力を保持",
                        label="サンプルレート",
                        info="「入力を保持」のままが推奨。SUNO は通常 48kHz、CD は 44100",
                    )
                    output_subtype_choice = gr.Dropdown(
                        choices=SUBTYPE_CHOICES,
                        value="入力を保持",
                        label="ビット深度 (subtype)",
                        info=(
                            "PCM_16=16-bit CD品質 / PCM_24=24-bit スタジオ標準 / "
                            "FLOAT=32-bit float 最高品質。DAW に持ち込むなら 24-bit か FLOAT"
                        ),
                    )
                    force_mono = gr.Checkbox(
                        label="ステレオ→モノラルに集約して処理(高速)",
                        value=False,
                        info=(
                            "OFF (推奨) = 入力がステレオなら L/R 独立処理してステレオで出力。"
                            "ON = モノラルに集約してから処理(処理時間半減、ステレオ幅は失う)"
                        ),
                    )

                with gr.Accordion("ステム合成 / 最終ミックス", open=False):
                    gr.Markdown(
                        "### 機能説明: ステム合成\n"
                        "**インストゥルメンタルや STEM (ドラム / ベース等) を一緒にアップロードして、"
                        "vo_fix が加工したボーカルと合成して1曲として書き出す** 機能です。\n\n"
                        "- 加工対象は「入力 (wav)」のボーカルのみ。下の追加ファイルは **そのまま** ミックスされる\n"
                        "- 複数ファイル選択可。ドラッグ&ドロップで複数まとめてOK\n"
                        "- サンプルレートはボーカルに合わせて自動リサンプル / チャンネル数は自動拡張\n"
                        "- 長さは **最も長いトラックに合わせ**、足りない箇所は無音でパディング(イントロ/アウトロのインストが生きる)\n"
                        "- ピーク 0.99 を超える場合は自動正規化(クリップ防止)"
                    )
                    stem_files = gr.File(
                        label="ステム / インストゥルメンタル(複数可)",
                        file_count="multiple",
                        type="filepath",
                        file_types=[".wav", ".flac", ".mp3"],
                    )
                    vocal_gain = gr.Slider(
                        -24, 12, value=0, step=0.5,
                        label="ボーカル ゲイン (dB)",
                        info="加工済みボーカルの音量。+ で前に / - で奥に",
                    )
                    stems_gain = gr.Slider(
                        -24, 12, value=0, step=0.5,
                        label="ステム ゲイン (dB)",
                        info="全ステム共通の音量。インストが大きすぎる時に -3 〜 -6dB 程度",
                    )
                    master_gain = gr.Slider(
                        -12, 6, value=0, step=0.5,
                        label="マスター ゲイン (dB)",
                        info="最終出力の音量。クリップしそうなら -1 〜 -3dB",
                    )

                with gr.Accordion("RVC 声質変換 (オプション)", open=False):
                    gr.Markdown(
                        "⚠️ vo_fix は RVC を内蔵していません。声質変換は Applio (https://applio.org/) で済ませてから vo_fix に渡すワークフローを推奨。"
                    )
                    rvc_model_path = gr.Textbox(label="RVC モデル(.pth)パス", value="")
                    rvc_index_path = gr.Textbox(label="RVC index(.index)パス", value="")
                    rvc_pitch = gr.Slider(-12, 12, value=0, step=1, label="RVC ピッチシフト (semitone)")

                run_btn = gr.Button("変換", variant="primary")

            with gr.Column():
                audio_out = gr.Audio(label="出力", type="filepath")
                status = gr.Textbox(label="ステータス", interactive=False)

                with gr.Accordion("操作ログ (履歴)", open=True):
                    gr.Markdown(
                        "_変換ごとに「どのプリセットから何を上書きしたか」を記録。"
                        "実体は `~/.vo_fix/logs/session-YYYYMMDD.jsonl` にも追記されます。_"
                    )
                    op_log_box = gr.Textbox(
                        value=OP_LOG.as_text(),
                        label="変換履歴",
                        lines=12,
                        max_lines=30,
                        interactive=False,
                    )
                    clear_log_btn = gr.Button("ログをクリア", size="sm")

        # --- Wiring ---
        # The component order here MUST match PARAM_FIELDS.
        all_param_inputs = [
            jitter_cents, vibrato_depth, vibrato_rate, shimmer,
            high_cut, presence_db, saturation, reverb_mix, reverb_room,
            skip_humanize, skip_effects, force_mono,
            rx_denoise_on, rx_denoise_db, rx_declick_on, rx_declick_sens, rx_plugin_dir,
            eq_low_shelf, eq_low_mid, eq_high_mid, eq_high_shelf,
            comp_on, comp_threshold, comp_ratio, comp_attack, comp_release,
            deess_on, deess_freq, deess_threshold, deess_ratio,
            chorus_on, chorus_rate, chorus_depth, chorus_mix,
            formant_shift, gender_shift,
            consonant_amount, consonant_sens,
            breath_on, breath_threshold, breath_min_silence, breath_intensity,
            output_sr_choice, output_subtype_choice,
        ]
        assert len(all_param_inputs) == len(PARAM_FIELDS), (
            f"UI/schema mismatch: {len(all_param_inputs)} inputs vs "
            f"{len(PARAM_FIELDS)} fields"
        )

        preset.change(
            load_preset_values,
            inputs=[preset],
            outputs=all_param_inputs,
        )

        save_btn.click(
            save_current_as_preset,
            inputs=[new_preset_name, preset, *all_param_inputs],
            outputs=[preset, preset_status],
        )

        delete_btn.click(
            delete_current_preset,
            inputs=[preset],
            outputs=[preset, preset_status],
        )

        clear_log_btn.click(clear_log, outputs=[op_log_box])

        export_btn.click(
            export_presets_action,
            outputs=[export_file, preset_status],
        )
        import_btn.click(
            import_presets_action,
            inputs=[import_file, import_overwrite],
            outputs=[preset, preset_status],
        )

        run_btn.click(
            run_wrapper,
            inputs=[
                audio_in, preset, *all_param_inputs,
                rvc_model_path, rvc_index_path, rvc_pitch,
                stem_files, vocal_gain, stems_gain, master_gain,
            ],
            outputs=[audio_out, status, op_log_box],
        )

    return demo


if __name__ == "__main__":
    build_ui().launch(theme=build_theme(), css=CUSTOM_CSS)
