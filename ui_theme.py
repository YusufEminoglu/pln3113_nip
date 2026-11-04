# -*- coding: utf-8 -*-
"""Palette-aware visual styling and stylesheet for PLN3113 NİP Analiz Stüdyosu.

Every colour the dock shows comes from :func:`studio_colors`. The colours are
derived from the QGIS palette and then pushed until each text colour reaches
WCAG AA (4.5:1) against every background it is drawn on. This matters for the
QGIS "Blend of Gray" theme, whose palette pairs a dark window with near-black
window text, and for "Night Mapping", whose window text is 2.9:1 on its window.
"""
from __future__ import annotations

from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QApplication, QAbstractSpinBox

AA = 4.5
# Tokens aim higher than AA: anti-aliased glyph stems draw a little lighter
# than their colour, and the measured text must still reach 4.5:1.
TEXT_TARGET = 5.0

# Semantic tones: (light-theme foreground, dark-theme foreground, light soft background)
_TONES = {
    "ok": ("#15803d", "#4ade80", "#dcfce7"),
    "bad": ("#b91c1c", "#f87171", "#fee2e2"),
    "warn": ("#92400e", "#fbbf24", "#fef3c7"),
    "info": ("#1d4ed8", "#93c5fd", "#e0f2fe"),
}


def _hex(color: QColor) -> str:
    """Format QColor to hex string #RRGGBB."""
    return color.name(QColor.NameFormat.HexRgb) if hasattr(QColor, "NameFormat") else color.name()


def _mix(first: QColor, second: QColor, amount: float) -> QColor:
    """Linearly interpolate two colors."""
    return QColor(
        round(first.red() * (1 - amount) + second.red() * amount),
        round(first.green() * (1 - amount) + second.green() * amount),
        round(first.blue() * (1 - amount) + second.blue() * amount),
    )


def contrast_ratio(first: QColor, second: QColor) -> float:
    """Calculate WCAG 2.1 contrast ratio between two colors."""
    def luminance(color: QColor) -> float:
        channels = [value / 255.0 for value in (color.red(), color.green(), color.blue())]
        channels = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(channels, (0.2126, 0.7152, 0.0722)))

    high, low = sorted((luminance(first), luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def ensure_contrast(color: QColor, backgrounds, target: float = AA) -> QColor:
    """Return ``color`` moved towards white or black until it reaches ``target``
    against every colour in ``backgrounds`` (the hue is kept as long as possible)."""
    backgrounds = list(backgrounds)

    def worst(candidate: QColor) -> float:
        return min(contrast_ratio(candidate, bg) for bg in backgrounds)

    if worst(color) >= target:
        return QColor(color)
    white, black = QColor("#ffffff"), QColor("#000000")
    best = None
    for extreme in (white, black):
        for step in range(1, 21):
            candidate = _mix(color, extreme, step / 20.0)
            if worst(candidate) >= target:
                if best is None or step < best[0]:
                    best = (step, candidate)
                break
    if best is not None:
        return best[1]
    return max((white, black), key=worst)


def studio_colors(palette: QPalette | None = None) -> dict[str, QColor]:
    """Derive palette-aware UI colours; every text colour is ≥ 4.5:1 on its backgrounds."""
    palette = palette or QApplication.palette()
    window = palette.color(QPalette.ColorRole.Window)
    pal_base = palette.color(QPalette.ColorRole.Base)
    dark = window.lightness() < 128
    white, black = QColor("#ffffff"), QColor("#000000")

    if dark:
        surface = QColor(window) if window.lightness() < 70 else _mix(window, black, 0.3)
        card = _mix(surface, white, 0.07)
        base = QColor(pal_base) if pal_base.lightness() < 100 else _mix(surface, black, 0.3)
    else:
        base = QColor(pal_base) if pal_base.lightness() >= 160 else QColor(white)
        surface = _mix(window, base, 0.65)
        card = QColor(base)

    accent_seed = QColor("#14b8a6" if dark else "#0f766e")
    active = _mix(surface, accent_seed, 0.22 if dark else 0.12)
    hover = _mix(surface, white if dark else black, 0.08)
    grounds = (surface, card, base, active, hover)

    text_seed = max(
        (palette.color(QPalette.ColorRole.WindowText), palette.color(QPalette.ColorRole.Text),
         QColor("#e5e7eb") if dark else QColor("#111827")),
        key=lambda c: min(contrast_ratio(c, bg) for bg in grounds),
    )
    text = ensure_contrast(text_seed, grounds, TEXT_TARGET)
    subtle = ensure_contrast(_mix(text, surface, 0.38), grounds, TEXT_TARGET)
    accent = ensure_contrast(accent_seed, grounds, TEXT_TARGET)
    accent_hover = ensure_contrast(QColor("#2dd4bf" if dark else "#115e59"), grounds, 3.0)
    border = _mix(text, surface, 0.78 if dark else 0.80)

    def filled(seed: str) -> tuple[QColor, QColor]:
        """A filled button colour and the text colour drawn on it (≥ 4.5:1)."""
        fill = QColor(seed)
        on = max((white, QColor("#0b1215")), key=lambda c: contrast_ratio(c, fill))
        if contrast_ratio(on, fill) < TEXT_TARGET:
            fill = ensure_contrast(fill, [on], TEXT_TARGET)
        return fill, on

    primary, on_accent = filled(_hex(accent) if not dark else "#14b8a6")
    secondary, on_secondary = filled("#38bdf8" if dark else "#0369a1")
    amber, on_amber = filled("#f59e0b" if dark else "#b45309")

    colors = {
        "window": window,
        "surface": surface,
        "card": card,
        "base": base,
        "text": text,
        "subtle": subtle,
        "border": border,
        "active": active,
        "hover": hover,
        "accent": accent,
        "accent_hover": accent_hover,
        "primary": primary,
        "on_accent": on_accent,
        "accent_secondary": secondary,
        "on_secondary": on_secondary,
        "accent_amber": amber,
        "on_amber": on_amber,
    }
    for tone, (light_fg, dark_fg, light_bg) in _TONES.items():
        bg = _mix(card, QColor(dark_fg), 0.16) if dark else QColor(light_bg)
        colors[f"{tone}_bg"] = bg
        colors[tone] = ensure_contrast(QColor(dark_fg if dark else light_fg), grounds + (bg,), TEXT_TARGET)
    return colors


def is_dark(colors: dict) -> bool:
    return colors["surface"].lightness() < 128


def hex_colors(palette: QPalette | None = None) -> dict[str, str]:
    """:func:`studio_colors` as ``#rrggbb`` strings (for style sheets and HTML)."""
    return {k: _hex(v) for k, v in studio_colors(palette).items()}


# ---------------------------------------------------------------------------
# Small style-sheet builders used by the dock (colours never written inline)
# ---------------------------------------------------------------------------
def text_css(role: str = "text", size: str = "", bold: bool = False, italic: bool = False,
             palette: QPalette | None = None) -> str:
    c = hex_colors(palette)
    parts = [f"color: {c[role]};"]
    if size:
        parts.append(f"font-size: {size};")
    if bold:
        parts.append("font-weight: 700;")
    if italic:
        parts.append("font-style: italic;")
    return " ".join(parts)


def note_css(tone: str = "info", size: str = "8.5pt", palette: QPalette | None = None) -> str:
    """A soft coloured box (banner, hint, chip) with its readable text colour."""
    c = hex_colors(palette)
    return (f"background: {c[tone + '_bg']}; color: {c[tone]}; border: 1px solid {c['border']}; "
            f"border-radius: 6px; padding: 6px; font-size: {size};")


def chip_css(tone: str | None = None, palette: QPalette | None = None) -> str:
    """A metric / verdict badge. ``tone`` None gives the neutral card colours."""
    c = hex_colors(palette)
    bg, fg = (c["active"], c["text"]) if tone is None else (c[tone + "_bg"], c[tone])
    return (f"background: {bg}; color: {fg}; padding: 4px 6px; border-radius: 6px; "
            f"font-size: 8pt; font-weight: 700;")


def chunk_css(tone: str, palette: QPalette | None = None) -> str:
    c = hex_colors(palette)
    return f"QProgressBar::chunk {{ background-color: {c[tone]}; }}"


def studio_stylesheet(palette: QPalette | None = None) -> str:
    """Generate dynamic stylesheet for PLN3113 NİP Studio Dock."""
    c = hex_colors(palette)
    return f"""
QWidget#TireNipDockWidget, QWidget#nipRoot {{
    background-color: {c['surface']};
    color: {c['text']};
    font-family: "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}}

QDockWidget#TireNipDockWidget {{
    color: {c['text']};
}}

QWidget#nipMainStack, QScrollArea#nipStackScroll > QWidget > QWidget {{
    background: {c['surface']};
}}

/* Header Banner */
QFrame#nipHeaderFrame {{
    background: {c['card']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    padding: 4px 8px;
}}

QLabel#nipHeroTitle {{
    font-size: 10.5pt;
    font-weight: 700;
    color: {c['text']};
}}

QLabel#nipHeaderSubtitle {{
    font-size: 8.5pt;
    color: {c['subtle']};
}}

QLabel#nipVersionBadge {{
    background: {c['active']};
    color: {c['accent']};
    border: 1px solid {c['border']};
    border-radius: 9px;
    padding: 1px 7px;
    font-size: 7.5pt;
    font-weight: 700;
}}

/* Vertical Icon Navigation Rail */
QListWidget#nipNavRail {{
    background: {c['card']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    outline: none;
    padding: 2px 1px;
}}

QListWidget#nipNavRail::item {{
    color: {c['subtle']};
    border-radius: 8px;
    border: none;
    border-left: 3px solid transparent;
    padding: 4px 1px 3px 1px;
    margin: 2px 1px;
    font-size: 7.5pt;
    font-weight: 600;
}}

QListWidget#nipNavRail::item:hover {{
    background: {c['hover']};
    color: {c['text']};
}}

QListWidget#nipNavRail::item:selected {{
    background: {c['active']};
    color: {c['accent']};
    border-left: 3px solid {c['accent']};
    font-weight: 700;
}}

/* Cards & GroupBoxes */
QGroupBox {{
    background: {c['card']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 9px;
    margin-top: 10px;
    padding: 16px 6px 6px 6px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    top: 2px;
    padding: 0 4px;
    color: {c['accent']};
    font-size: 9pt;
    font-weight: 700;
}}

QFrame#nipCard {{
    background: {c['card']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 8px;
}}

QFrame#nipAccentCard {{
    background: {c['active']};
    border: 1px solid {c['border']};
    border-left: 4px solid {c['accent']};
    border-radius: 8px;
    padding: 6px;
}}

QFrame#nipAccentCard QLabel {{
    background: transparent;
}}

/* Form Controls */
QLabel {{
    color: {c['text']};
    font-size: 8.5pt;
}}

QCheckBox, QRadioButton {{
    color: {c['text']};
}}

QComboBox, QLineEdit {{
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 4px 6px;
    background-color: {c['base']};
    color: {c['text']};
    font-size: 8.5pt;
}}

QComboBox:focus, QLineEdit:focus {{
    border: 1px solid {c['accent']};
}}

QComboBox QAbstractItemView {{
    background-color: {c['base']};
    color: {c['text']};
    selection-background-color: {c['active']};
    selection-color: {c['text']};
}}

/* Spin boxes: colour only (a background or border blanks the arrows on Qt6). */
QSpinBox, QDoubleSpinBox {{
    color: {c['text']};
    font-size: 8.5pt;
}}

/* Buttons */
QPushButton {{
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 5px 8px;
    font-weight: 600;
    font-size: 8.5pt;
    background-color: {c['card']};
    color: {c['text']};
}}

QPushButton:hover {{
    border-color: {c['accent']};
    color: {c['accent']};
    background-color: {c['hover']};
}}

QPushButton:disabled {{
    color: {c['subtle']};
    background-color: {c['surface']};
}}

QPushButton#PrimaryButton, QPushButton#nipPrimary {{
    background-color: {c['primary']};
    color: {c['on_accent']};
    border: 1px solid {c['primary']};
    font-weight: 700;
}}

QPushButton#PrimaryButton:hover, QPushButton#nipPrimary:hover {{
    background-color: {c['primary']};
    color: {c['on_accent']};
    border: 2px solid {c['accent_hover']};
}}

QPushButton#CleanButton {{
    background-color: {c['accent_secondary']};
    color: {c['on_secondary']};
    border: 1px solid {c['accent_secondary']};
    font-weight: 700;
}}

QPushButton#FieldButton {{
    background-color: {c['accent_amber']};
    color: {c['on_amber']};
    border: 1px solid {c['accent_amber']};
    font-weight: 700;
}}

QPushButton#CleanButton:hover, QPushButton#FieldButton:hover {{
    border: 2px solid {c['text']};
}}

QPushButton#PrimaryButton:disabled, QPushButton#CleanButton:disabled, QPushButton#FieldButton:disabled {{
    background-color: {c['surface']};
    color: {c['subtle']};
    border: 1px solid {c['border']};
}}

/* Tables */
QTableWidget, QTextEdit, QListWidget {{
    background-color: {c['base']};
    alternate-background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    gridline-color: {c['border']};
    font-size: 8pt;
    color: {c['text']};
}}

QHeaderView::section {{
    background-color: {c['active']};
    color: {c['text']};
    padding: 4px;
    font-weight: bold;
    border: none;
    border-right: 1px solid {c['border']};
    border-bottom: 1px solid {c['border']};
}}

/* Sub Tab Widget (Results) */
QTabWidget::pane {{
    border: 1px solid {c['border']};
    background: {c['card']};
    border-radius: 6px;
    top: -1px;
}}

QTabBar::tab {{
    background: {c['surface']};
    color: {c['subtle']};
    padding: 5px 8px;
    font-weight: 600;
    font-size: 8pt;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}}

QTabBar::tab:selected {{
    background: {c['card']};
    color: {c['accent']};
    border-bottom: 2px solid {c['accent']};
    font-weight: 700;
}}

/* Progress Bar */
QProgressBar {{
    border: 1px solid {c['border']};
    border-radius: 4px;
    text-align: center;
    background-color: {c['surface']};
    color: {c['text']};
    font-size: 8pt;
}}

QProgressBar::chunk {{
    background-color: {c['primary']};
    border-radius: 3px;
}}

/* Scroll Area & Bars */
QScrollArea {{
    border: none;
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 2px 0;
}}

QScrollBar::handle:vertical {{
    background: {c['border']};
    border-radius: 3px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c['accent']};
}}
"""


def apply_native_editor_theme(root, palette: QPalette | None = None) -> None:
    """Windows spin panels ignore Base; colour their editor without replacing arrows."""
    colors = studio_colors(palette)
    editor_style = f"background: {_hex(colors['base'])}; color: {_hex(colors['text'])}; border: 0; padding: 2px;"
    for spin in root.findChildren(QAbstractSpinBox):
        spin.lineEdit().setStyleSheet(editor_style)
