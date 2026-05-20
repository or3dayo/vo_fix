"""Gradio UI for vo_fix.

Run: python app.py
Opens http://localhost:7860
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import gradio as gr
import numpy as np
import soundfile as sf

from vo_fix.effects import EffectsConfig
from vo_fix.humanize import HumanizeConfig
from vo_fix.io import load_wav
from vo_fix.pipeline import PRESETS, ProcessConfig, RXConfig, process_array
from vo_fix.vst import DEFAULT_RX_DIR, find_rx_plugins


def run(
    audio_path,
    preset,
    jitter_cents,
    vibrato_depth,
    vibrato_rate,
    shimmer,
    high_cut,
    presence_db,
    saturation,
    reverb_mix,
    reverb_room,
    skip_humanize,
    skip_effects,
    rx_denoise_on,
    rx_denoise_db,
    rx_declick_on,
    rx_declick_sens,
    rx_plugin_dir,
    rvc_model_path,
    rvc_index_path,
    rvc_pitch,
):
    if audio_path is None:
        return None, "音声ファイルをアップロードしてください"

    base = PRESETS[preset]
    cfg = ProcessConfig(
        humanize=HumanizeConfig(
            jitter_cents=float(jitter_cents),
            vibrato_depth_cents=float(vibrato_depth),
            vibrato_rate_hz=float(vibrato_rate),
            shimmer=float(shimmer),
            jitter_rate_hz=base.humanize.jitter_rate_hz,
            shimmer_rate_hz=base.humanize.shimmer_rate_hz,
        ),
        effects=EffectsConfig(
            high_cut_hz=float(high_cut),
            presence_db=float(presence_db),
            saturation=float(saturation),
            reverb_mix=float(reverb_mix),
            reverb_room=float(reverb_room),
        ),
        rx=RXConfig(
            voice_denoise_enabled=bool(rx_denoise_on),
            voice_denoise_reduction_db=float(rx_denoise_db),
            declick_enabled=bool(rx_declick_on),
            declick_sensitivity=float(rx_declick_sens),
            plugin_dir=rx_plugin_dir or None,
        ),
        target_sr=base.target_sr,
        skip_humanize=skip_humanize,
        skip_effects=skip_effects,
    )
    if rvc_model_path:
        cfg.rvc_model_path = rvc_model_path
        cfg.rvc_index_path = rvc_index_path or None
        cfg.rvc_pitch_semitones = float(rvc_pitch)

    try:
        samples, sr = load_wav(audio_path, target_sr=cfg.target_sr)
        out, out_sr = process_array(samples, sr, cfg)
        out_path = Path(tempfile.mkdtemp()) / "vo_fix_out.wav"
        sf.write(str(out_path), out.astype(np.float32), out_sr, subtype="PCM_16")
        return str(out_path), f"完了 — {len(out)/out_sr:.2f}s @ {out_sr}Hz"
    except Exception as e:
        return None, f"エラー: {e}"


def load_preset_values(preset_name):
    p = PRESETS[preset_name]
    return (
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
    )


def build_ui():
    with gr.Blocks(title="vo_fix — AI歌声ナチュラライザー") as demo:
        gr.Markdown("# vo_fix — AI歌声ナチュラライザー\nSUNO等のAI歌声に揺らぎとミックス処理を足して人間っぽくします。")

        with gr.Row():
            with gr.Column():
                audio_in = gr.Audio(label="入力 (wav)", type="filepath")
                preset = gr.Dropdown(
                    choices=list(PRESETS.keys()),
                    value="natural",
                    label="プリセット",
                    info="出発点。下のスライダーを動かすと上書きされる",
                )
                gr.Markdown(
                    "**プリセットの使い分け**  \n"
                    "🔘 **off** — 何もしない(処理前との比較用)  \n"
                    "🟢 **natural** — 自然な揺らぎ + 軽いミックス。迷ったらコレ  \n"
                    "💜 **intimate** — 揺らぎ強め + リバーブ深め。バラード・ささやき・しっとり系  \n"
                    "💡 **polished** — 揺らぎ控えめ + 高域明るめ + リバーブ薄め。前に出したいポップス向け"
                )

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

                with gr.Accordion("エフェクト", open=True):
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
                        info="チェックすると EQ/歪み/リバーブを全て飛ばす(揺らぎだけ掛けたい時用)",
                    )

                with gr.Accordion("iZotope RX 前処理 (オプション)", open=False):
                    rx_found = find_rx_plugins()
                    if rx_found:
                        gr.Markdown(f"✅ 検出: {', '.join(rx_found.keys())}")
                    else:
                        gr.Markdown(f"⚠️ RX VST3 が `{DEFAULT_RX_DIR}` に見つかりません。下のパス欄で指定してください。")
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
                    rx_plugin_dir = gr.Textbox(
                        label="VST3 ディレクトリ (空欄でデフォルト)", value="",
                        info=f"デフォルトは {DEFAULT_RX_DIR}",
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

        preset.change(
            load_preset_values,
            inputs=[preset],
            outputs=[
                jitter_cents, vibrato_depth, vibrato_rate, shimmer,
                high_cut, presence_db, saturation, reverb_mix, reverb_room,
                skip_humanize, skip_effects,
            ],
        )

        run_btn.click(
            run,
            inputs=[
                audio_in, preset, jitter_cents, vibrato_depth, vibrato_rate, shimmer,
                high_cut, presence_db, saturation, reverb_mix, reverb_room,
                skip_humanize, skip_effects,
                rx_denoise_on, rx_denoise_db, rx_declick_on, rx_declick_sens, rx_plugin_dir,
                rvc_model_path, rvc_index_path, rvc_pitch,
            ],
            outputs=[audio_out, status],
        )

    return demo


if __name__ == "__main__":
    build_ui().launch()
