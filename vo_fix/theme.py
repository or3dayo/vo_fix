"""Spotify-inspired Gradio theme for vo_fix.

Reference tokens (publicly known Spotify brand):
    Brand green:      #1DB954 (classic) / #1ED760 (newer)
    Background base:  #121212
    Surface:          #181818
    Surface elevated: #282828
    Border:           #2A2A2A
    Text primary:     #FFFFFF
    Text subdued:     #B3B3B3
    Text tertiary:    #7A7A7A

We map these onto Gradio's theme primitives and patch the rest via CSS.
"""

from __future__ import annotations

import gradio as gr


SPOTIFY_GREEN = "#1ED760"
SPOTIFY_GREEN_HOVER = "#1FDF64"
SPOTIFY_GREEN_DARK = "#169C46"

BG_BASE = "#121212"
BG_SURFACE = "#181818"
BG_ELEVATED = "#282828"
BG_INPUT = "#2A2A2A"
BORDER = "#2A2A2A"
BORDER_STRONG = "#404040"

TEXT_PRIMARY = "#FFFFFF"
TEXT_SUBDUED = "#B3B3B3"
TEXT_TERTIARY = "#7A7A7A"


def build_theme() -> gr.themes.Base:
    """Return a Gradio theme configured with Spotify-like palette + fonts."""
    primary = gr.themes.Color(
        c50="#e7faec", c100="#c3f1d0", c200="#9fe7b3", c300="#7bde96",
        c400="#57d479", c500=SPOTIFY_GREEN, c600=SPOTIFY_GREEN_HOVER,
        c700=SPOTIFY_GREEN_DARK, c800="#0e7634", c900="#0a5325", c950="#063017",
    )
    neutral = gr.themes.Color(
        c50="#f5f5f5", c100="#e5e5e5", c200="#d4d4d4", c300="#a3a3a3",
        c400="#737373", c500="#525252", c600="#404040", c700="#282828",
        c800=BG_SURFACE, c900=BG_BASE, c950="#000000",
    )

    theme = gr.themes.Base(
        primary_hue=primary,
        secondary_hue=primary,
        neutral_hue=neutral,
        radius_size=gr.themes.sizes.radius_md,
        font=[gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"],
        font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"],
    ).set(
        # Page chrome
        body_background_fill=BG_BASE,
        body_background_fill_dark=BG_BASE,
        body_text_color=TEXT_PRIMARY,
        body_text_color_subdued=TEXT_SUBDUED,
        background_fill_primary=BG_SURFACE,
        background_fill_secondary=BG_ELEVATED,
        # Blocks (cards / accordions)
        block_background_fill=BG_SURFACE,
        block_border_color=BORDER,
        block_border_width="1px",
        block_label_background_fill=BG_SURFACE,
        block_label_text_color=TEXT_SUBDUED,
        block_label_text_weight="600",
        block_title_text_color=TEXT_PRIMARY,
        block_title_text_weight="700",
        block_radius="8px",
        # Inputs
        input_background_fill=BG_INPUT,
        input_background_fill_focus=BG_INPUT,
        input_border_color=BORDER,
        input_border_color_focus=SPOTIFY_GREEN,
        input_placeholder_color=TEXT_TERTIARY,
        # Sliders
        slider_color=SPOTIFY_GREEN,
        # Primary button: Spotify green pill
        button_primary_background_fill=SPOTIFY_GREEN,
        button_primary_background_fill_hover=SPOTIFY_GREEN_HOVER,
        button_primary_text_color="#000000",
        button_primary_text_color_hover="#000000",
        button_primary_border_color=SPOTIFY_GREEN,
        button_primary_border_color_hover=SPOTIFY_GREEN_HOVER,
        # Secondary button: dark pill
        button_secondary_background_fill=BG_ELEVATED,
        button_secondary_background_fill_hover="#3E3E3E",
        button_secondary_text_color=TEXT_PRIMARY,
        button_secondary_text_color_hover=TEXT_PRIMARY,
        button_secondary_border_color=BORDER_STRONG,
        # Borders
        border_color_accent=SPOTIFY_GREEN,
        border_color_primary=BORDER,
    )
    return theme


# Custom CSS that the theme API doesn't quite express: pill buttons,
# brand header banner, accordion hover lift, slider thumb color.
CUSTOM_CSS = f"""
/* Body / page */
body, .gradio-container {{
    background: {BG_BASE} !important;
    color: {TEXT_PRIMARY} !important;
}}

/* Brand header */
.vo-fix-brand {{
    background: linear-gradient(135deg, #0a4a22 0%, {BG_BASE} 60%);
    padding: 24px 28px;
    border-radius: 12px;
    margin-bottom: 16px;
    border: 1px solid {BORDER};
}}
.vo-fix-brand h1 {{
    color: {TEXT_PRIMARY} !important;
    font-size: 32px !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em !important;
    margin: 0 0 6px 0 !important;
    display: flex;
    align-items: center;
    gap: 12px;
}}
.vo-fix-brand h1::before {{
    content: "";
    display: inline-block;
    width: 12px; height: 12px;
    background: {SPOTIFY_GREEN};
    border-radius: 50%;
    box-shadow: 0 0 16px {SPOTIFY_GREEN};
}}
.vo-fix-brand p {{
    color: {TEXT_SUBDUED} !important;
    margin: 0 !important;
    font-size: 14px;
}}

/* Buttons -> pill */
button.lg.primary, button.primary, .gr-button.primary {{
    border-radius: 500px !important;
    font-weight: 700 !important;
    text-transform: none !important;
    letter-spacing: 0.01em !important;
    transition: transform 0.12s ease, background 0.12s ease !important;
    padding: 10px 24px !important;
}}
button.lg.primary:hover, button.primary:hover, .gr-button.primary:hover {{
    transform: scale(1.04);
}}
button.secondary, .gr-button.secondary {{
    border-radius: 500px !important;
    font-weight: 600 !important;
}}

/* Headings inside content */
h1, h2, h3 {{
    color: {TEXT_PRIMARY} !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em !important;
}}
h3 {{
    font-size: 17px !important;
    margin-top: 4px !important;
}}

/* Markdown blocks: soften body copy color */
.prose, .markdown {{
    color: {TEXT_SUBDUED} !important;
}}
.prose strong, .markdown strong {{
    color: {TEXT_PRIMARY} !important;
}}
.prose em, .markdown em {{
    color: {TEXT_TERTIARY} !important;
}}

/* Accordion hover lift */
.gr-accordion, .label-wrap {{
    transition: background 0.15s ease;
}}
.label-wrap:hover {{
    background: rgba(255, 255, 255, 0.02);
}}

/* Slider thumb glow */
input[type=range]::-webkit-slider-thumb {{
    background: {SPOTIFY_GREEN} !important;
    box-shadow: 0 0 8px rgba(30, 215, 96, 0.5) !important;
}}
input[type=range]::-moz-range-thumb {{
    background: {SPOTIFY_GREEN} !important;
}}

/* Slider track fill (Gradio uses CSS variables internally for some browsers) */
.slider-handle {{
    background: {SPOTIFY_GREEN} !important;
}}

/* Status / log Textbox: monospace, dark */
textarea[readonly] {{
    font-family: "JetBrains Mono", ui-monospace, monospace !important;
    background: {BG_BASE} !important;
    color: {TEXT_SUBDUED} !important;
    border-color: {BORDER} !important;
}}

/* Tighten section gap */
.gradio-container .form {{
    gap: 8px;
}}

/* Audio player tweaks */
audio {{
    filter: invert(0.85) hue-rotate(180deg);
}}
"""
