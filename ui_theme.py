# -*- coding: utf-8 -*-
"""Palette-aware visual styling and stylesheet for PLN3113 NİP Analiz Stüdyosu.

DEÜ Mimarlık Fakültesi Şehir ve Bölge Planlama Bölümü
PLN3113 - Tire NİP Analiz Stüdyosu
"""
from __future__ import annotations

from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QApplication, QAbstractSpinBox


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


def studio_colors(palette: QPalette | None = None) -> dict[str, QColor]:
    """Derive palette-aware UI color definitions adapted to QGIS Light/Dark themes."""
    palette = palette or QApplication.palette()
    window = palette.color(QPalette.ColorRole.Window)
    base = palette.color(QPalette.ColorRole.Base)
    text = palette.color(QPalette.ColorRole.WindowText)
    dark = window.lightness() < 128

    # Signature DEÜ ŞBP Emerald/Teal accent
    accent = QColor("#14b8a6" if dark else "#0f766e")
    accent_hover = QColor("#2dd4bf" if dark else "#115e59")
    accent_secondary = QColor("#38bdf8" if dark else "#0284c7")
    accent_amber = QColor("#f59e0b" if dark else "#d97706")

    surface = _mix(window, QColor("#ffffff"), 0.06) if dark else _mix(window, base, 0.65)
    card = _mix(window, QColor("#ffffff"), 0.11) if dark else base
    border = _mix(text, surface, 0.78 if dark else 0.86)
    subtle = _mix(text, surface, 0.40 if dark else 0.38)
    active = _mix(surface, accent, 0.22 if dark else 0.12)
    hover = _mix(surface, text, 0.08)

    on_accent = max(
        (QColor("#ffffff"), QColor("#091e22")),
        key=lambda c: contrast_ratio(c, accent)
    )

    return {
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
        "accent_secondary": accent_secondary,
        "accent_amber": accent_amber,
        "on_accent": on_accent,
    }


def studio_stylesheet(palette: QPalette | None = None) -> str:
    """Generate dynamic stylesheet for PLN3113 NİP Studio Dock."""
    c = {k: _hex(v) for k, v in studio_colors(palette).items()}
    return f"""
QWidget#TireNipDockWidget, QWidget#nipRoot {{
    background-color: {c['surface']};
    color: {c['text']};
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
}}

/* Header Banner */
QFrame#nipHeaderFrame {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {c['card']}, stop:1 {c['surface']});
    border: 1px solid {c['border']};
    border-radius: 10px;
    padding: 6px 10px;
}}

QLabel#nipHeroTitle {{
    font-size: 11pt;
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

QToolButton#nipHeaderGuideBtn {{
    background: {c['active']};
    color: {c['accent']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 4px 10px;
    font-weight: 600;
    font-size: 8pt;
}}

QToolButton#nipHeaderGuideBtn:hover {{
    background: {c['accent']};
    color: {c['on_accent']};
    border-color: {c['accent']};
}}

/* Vertical Icon Navigation Rail */
QListWidget#nipNavRail {{
    background: {c['card']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    outline: none;
    padding: 4px 2px;
}}

QListWidget#nipNavRail::item {{
    color: {c['subtle']};
    border-radius: 8px;
    border: none;
    border-left: 3px solid transparent;
    padding: 8px 2px 6px 2px;
    margin: 3px 2px;
    font-size: 8pt;
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
    border: 1px solid {c['border']};
    border-radius: 9px;
    margin-top: 10px;
    padding: 18px 8px 8px 8px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    top: 2px;
    padding: 0 4px;
    color: {c['accent']};
    font-size: 9pt;
    font-weight: 700;
}}

/* Inner Cards */
QFrame#nipCard {{
    background: {c['card']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 10px;
}}

QFrame#nipAccentCard {{
    background: {c['active']};
    border: 1px solid {c['border']};
    border-left: 4px solid {c['accent']};
    border-radius: 8px;
    padding: 10px;
}}

/* Form Controls */
QLabel {{
    color: {c['text']};
    font-size: 8.5pt;
}}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 5px 8px;
    background-color: {c['base']};
    color: {c['text']};
    font-size: 8.5pt;
}}

QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border: 1.5px solid {c['accent']};
}}

/* Buttons */
QPushButton {{
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 6px 12px;
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

QPushButton#PrimaryButton, QPushButton#nipPrimary {{
    background-color: {c['accent']};
    color: {c['on_accent']};
    border: 1px solid {c['accent']};
    font-weight: 700;
}}

QPushButton#PrimaryButton:hover, QPushButton#nipPrimary:hover {{
    background-color: {c['accent_hover']};
    border-color: {c['accent_hover']};
}}

QPushButton#CleanButton {{
    background-color: {c['accent_secondary']};
    color: #ffffff;
    border: 1px solid {c['accent_secondary']};
    font-weight: 700;
}}

QPushButton#CleanButton:hover {{
    background-color: #0369a1;
}}

QPushButton#FieldButton {{
    background-color: {c['accent_amber']};
    color: #ffffff;
    border: 1px solid {c['accent_amber']};
    font-weight: 700;
}}

QPushButton#FieldButton:hover {{
    background-color: #b45309;
}}

/* Tables */
QTableWidget {{
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
    padding: 5px;
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
    padding: 6px 12px;
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
    font-size: 8pt;
}}

QProgressBar::chunk {{
    background-color: {c['accent']};
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


# Static stylesheet constant for backwards compatibility
NIP_STUDIO_QSS = studio_stylesheet()
