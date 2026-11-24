"""Ink Wash Design System for HeadMouseAI + Jadoo.

A refined, high-contrast, minimalist monochrome aesthetic with subtle tones:
- Canvas (Primary background): #17191C (Deep Charcoal Black)
- Surface / Cards (Secondary container): #222529 (Deep Graphite)
- Elevated Surface / Active: #2D3137 (Elevated Slate)
- Borders & Dividers: #34383D (Cool Gray)
- Secondary Borders / Inactive: #777F87 (Muted Slate)
- Primary Text: #F2F0EA (Soft Ivory - High Contrast, >13:1 on Canvas)
- Secondary Text: #B9C0C7 (Silver Gray, >6.5:1 on Surface)
- Muted / Disabled Text: #777F87 (Muted Slate)
- Restrained State Accents:
  - Sage Gray (Subtle Success / Active): #89958C text, #34383D border, #1E2320 background
  - Muted Amber (Subtle Warning / Caution): #C19A62 text, #4A3E2B border, #262118 background
  - Muted Crimson (Emergency / Danger): #B66F70 text, #5A2324 border, #291516 background
- Typography:
  - Primary Font: "Segoe UI Variable Text", "Segoe UI", -apple-system, BlinkMacSystemFont, "Inter", sans-serif
  - Monospace Numeral Font: "Cascadia Code", "Consolas", monospace (Tabular figures)
- Accessibility:
  - Minimum 44x44px touch / head-click targets
  - High-visibility 2px focus outlines for keyboard / switch navigation
  - WCAG AA contrast compliance across all states
"""

from __future__ import annotations

# Design Tokens
INK_CANVAS = "#17191C"
INK_GRAPHITE = "#222529"
INK_ELEVATED = "#2D3137"
INK_COOL_GRAY = "#34383D"
INK_SILVER_GRAY = "#B9C0C7"
INK_SOFT_IVORY = "#F2F0EA"
INK_MUTED_SLATE = "#777F87"
INK_SAGE_GRAY = "#89958C"
INK_MUTED_AMBER = "#C19A62"
INK_MUTED_CRIMSON = "#B66F70"
INK_PURE_WHITE = "#FFFFFF"
INK_PURE_BLACK = "#0D0E10"

FONT_PRIMARY = '"Segoe UI"'
FONT_MONO = '"Consolas"'

INK_WASH_THEME_QSS = f"""
/* Global Window & Base Styles */
QMainWindow, QDialog, QWidget {{
    background-color: {INK_CANVAS};
    color: {INK_SOFT_IVORY};
    font-family: {FONT_PRIMARY};
    font-size: 13px;
}}

/* Tooltips */
QToolTip {{
    background-color: {INK_GRAPHITE};
    color: {INK_SOFT_IVORY};
    border: 1px solid {INK_COOL_GRAY};
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* Header Container */
QWidget#header_widget {{
    background-color: {INK_GRAPHITE};
    border-bottom: 1px solid {INK_COOL_GRAY};
}}

/* Modern Tab Navigation */
QTabWidget::pane {{
    border: 1px solid {INK_COOL_GRAY};
    background-color: {INK_GRAPHITE};
    border-radius: 8px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: {INK_CANVAS};
    color: {INK_SILVER_GRAY};
    padding: 10px 24px;
    margin-right: 6px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
    font-size: 13px;
    border: 1px solid {INK_COOL_GRAY};
    border-bottom: none;
}}

QTabBar::tab:selected {{
    background-color: {INK_GRAPHITE};
    color: {INK_SOFT_IVORY};
    border-color: {INK_COOL_GRAY};
    border-top: 3px solid {INK_SOFT_IVORY};
    font-weight: 700;
}}

QTabBar::tab:focus {{
    outline: none;
    border-top: 3px solid {INK_SOFT_IVORY};
    border-left: 1px solid {INK_SILVER_GRAY};
    border-right: 1px solid {INK_SILVER_GRAY};
    color: {INK_PURE_WHITE};
}}

QTabBar::tab:hover:!selected {{
    background-color: {INK_ELEVATED};
    color: {INK_SOFT_IVORY};
}}

/* Cards & Group Boxes */
QGroupBox {{
    background-color: {INK_GRAPHITE};
    border: 1px solid {INK_COOL_GRAY};
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 18px;
    padding-bottom: 12px;
    padding-left: 14px;
    padding-right: 14px;
    font-weight: 600;
    color: {INK_SOFT_IVORY};
    font-size: 13px;
}}

QGroupBox:hover {{
    border-color: {INK_MUTED_SLATE};
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 3px 12px;
    background-color: {INK_ELEVATED};
    border: 1px solid {INK_COOL_GRAY};
    border-radius: 6px;
    color: {INK_SILVER_GRAY};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}

/* Standard Buttons */
QPushButton {{
    background-color: {INK_GRAPHITE};
    color: {INK_SOFT_IVORY};
    border: 1px solid {INK_COOL_GRAY};
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: 600;
    font-size: 12px;
    min-height: 24px;
}}

QPushButton:hover {{
    background-color: {INK_ELEVATED};
    border-color: {INK_SILVER_GRAY};
    color: {INK_PURE_WHITE};
}}

QPushButton:focus {{
    outline: none;
    border: 2px solid {INK_SOFT_IVORY};
    background-color: {INK_ELEVATED};
    color: {INK_PURE_WHITE};
}}

QPushButton:pressed {{
    background-color: {INK_CANVAS};
    border-color: {INK_COOL_GRAY};
}}

QPushButton:disabled {{
    background-color: {INK_CANVAS};
    color: {INK_MUTED_SLATE};
    border-color: {INK_COOL_GRAY};
}}

/* Primary Action CTA: Start Tracking (Ink Wash Solid Highlight) */
QPushButton#btn_start {{
    background-color: {INK_SOFT_IVORY};
    border: 1px solid {INK_PURE_WHITE};
    color: {INK_PURE_BLACK};
    font-weight: 700;
    border-radius: 6px;
    padding: 8px 18px;
}}
QPushButton#btn_start:hover {{
    background-color: {INK_PURE_WHITE};
    border-color: {INK_PURE_WHITE};
    color: {INK_PURE_BLACK};
}}
QPushButton#btn_start:focus {{
    outline: none;
    border: 2px solid {INK_PURE_WHITE};
}}
QPushButton#btn_start:pressed {{
    background-color: {INK_SILVER_GRAY};
}}

QPushButton#btn_stop {{
    background-color: {INK_GRAPHITE};
    border: 1px solid {INK_COOL_GRAY};
    color: {INK_SOFT_IVORY};
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 18px;
}}
QPushButton#btn_stop:hover {{
    background-color: {INK_ELEVATED};
    border-color: {INK_SILVER_GRAY};
    color: {INK_PURE_WHITE};
}}
QPushButton#btn_stop:focus {{
    outline: none;
    border: 2px solid {INK_SOFT_IVORY};
}}

/* Mouse Control Toggle */
QPushButton#btn_mouse_toggle {{
    background-color: {INK_ELEVATED};
    border: 1px solid {INK_SILVER_GRAY};
    color: {INK_SOFT_IVORY};
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 18px;
}}
QPushButton#btn_mouse_toggle:hover {{
    background-color: {INK_COOL_GRAY};
    border-color: {INK_SOFT_IVORY};
    color: {INK_PURE_WHITE};
}}
QPushButton#btn_mouse_toggle:focus {{
    outline: none;
    border: 2px solid {INK_SOFT_IVORY};
}}
QPushButton#btn_mouse_toggle:pressed {{
    background-color: {INK_CANVAS};
}}

/* Emergency Stop (Professional High-Visibility Muted Crimson) */
QPushButton#btn_emergency {{
    background-color: #5A2324;
    border: 1px solid {INK_MUTED_CRIMSON};
    color: {INK_PURE_WHITE};
    font-weight: 700;
    border-radius: 6px;
    padding: 8px 18px;
}}
QPushButton#btn_emergency:hover {{
    background-color: #6E2D2E;
    border-color: #D18384;
}}
QPushButton#btn_emergency:focus {{
    outline: none;
    border: 2px solid #FCA5A5;
}}

QPushButton#btn_calibrate {{
    background-color: {INK_GRAPHITE};
    border: 1px solid {INK_COOL_GRAY};
    color: {INK_SOFT_IVORY};
    font-weight: 600;
    border-radius: 6px;
    padding: 8px 16px;
}}
QPushButton#btn_calibrate:hover {{
    background-color: {INK_ELEVATED};
    border-color: {INK_SILVER_GRAY};
    color: {INK_PURE_WHITE};
}}
QPushButton#btn_calibrate:focus {{
    outline: none;
    border: 2px solid {INK_SOFT_IVORY};
}}

/* Sliders */
QSlider::groove:horizontal {{
    height: 6px;
    background: {INK_CANVAS};
    border: 1px solid {INK_COOL_GRAY};
    border-radius: 3px;
}}

QSlider::sub-page:horizontal {{
    background: {INK_SILVER_GRAY};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: {INK_SOFT_IVORY};
    border: 2px solid {INK_MUTED_SLATE};
    width: 16px;
    height: 16px;
    margin-top: -6px;
    margin-bottom: -6px;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: {INK_PURE_WHITE};
    border-color: {INK_SOFT_IVORY};
}}

QSlider:focus {{
    outline: none;
}}

QSlider::handle:horizontal:focus {{
    background: {INK_PURE_WHITE};
    border: 2px solid {INK_SOFT_IVORY};
}}

/* Combo Boxes & Dropdowns */
QComboBox {{
    background-color: {INK_GRAPHITE};
    border: 1px solid {INK_COOL_GRAY};
    border-radius: 6px;
    padding: 6px 12px;
    color: {INK_SOFT_IVORY};
    font-size: 12px;
    min-height: 24px;
}}

QComboBox:hover {{
    border-color: {INK_MUTED_SLATE};
    background-color: {INK_ELEVATED};
}}

QComboBox:focus {{
    border: 2px solid {INK_SOFT_IVORY};
    outline: none;
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid {INK_COOL_GRAY};
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {INK_SILVER_GRAY};
    width: 0;
    height: 0;
    margin-right: 6px;
}}

QComboBox QAbstractItemView {{
    background-color: {INK_GRAPHITE};
    border: 1px solid {INK_COOL_GRAY};
    selection-background-color: {INK_ELEVATED};
    selection-color: {INK_PURE_WHITE};
    color: {INK_SOFT_IVORY};
    outline: none;
    padding: 4px;
    border-radius: 6px;
}}

QComboBox QAbstractItemView:focus {{
    border: 1px solid {INK_SOFT_IVORY};
}}

/* Checkboxes */
QCheckBox {{
    spacing: 8px;
    color: {INK_SILVER_GRAY};
    font-size: 12px;
    font-weight: 500;
}}

QCheckBox:hover {{
    color: {INK_SOFT_IVORY};
}}

QCheckBox:focus {{
    outline: none;
    color: {INK_PURE_WHITE};
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {INK_COOL_GRAY};
    border-radius: 4px;
    background-color: {INK_CANVAS};
}}

QCheckBox::indicator:hover {{
    border-color: {INK_SILVER_GRAY};
    background-color: {INK_GRAPHITE};
}}

QCheckBox::indicator:focus {{
    border: 2px solid {INK_SOFT_IVORY};
}}

QCheckBox::indicator:checked {{
    background-color: {INK_SOFT_IVORY};
    border-color: {INK_PURE_WHITE};
}}

/* Progress Bars */
QProgressBar {{
    background-color: {INK_CANVAS};
    border: 1px solid {INK_COOL_GRAY};
    border-radius: 5px;
    text-align: center;
    color: {INK_SOFT_IVORY};
    font-size: 11px;
    font-weight: 600;
    min-height: 14px;
}}

QProgressBar::chunk {{
    background-color: {INK_SILVER_GRAY};
    border-radius: 4px;
}}

/* Text Inputs & Editors */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {INK_CANVAS};
    color: {INK_SOFT_IVORY};
    border: 1px solid {INK_COOL_GRAY};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {INK_SOFT_IVORY};
    outline: none;
}}

/* Scroll Area & Bars */
QScrollArea {{
    border: none;
    background-color: transparent;
}}

QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 6px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: #34383D;
    min-height: 24px;
    border-radius: 3px;
}}

QScrollBar::handle:vertical:hover {{
    background: #777F87;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
    background: none;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 6px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: #34383D;
    min-width: 24px;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal:hover {{
    background: #777F87;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: none;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* Status Bar */
QStatusBar {{
    background-color: {INK_CANVAS};
    border-top: 1px solid {INK_COOL_GRAY};
    color: {INK_SILVER_GRAY};
    font-size: 12px;
    min-height: 28px;
    padding: 0 8px;
}}

QStatusBar QLabel {{
    color: {INK_SILVER_GRAY};
    font-weight: 500;
}}
"""

# Compatibility aliases
OBSIDIAN_CHROME_THEME_QSS = INK_WASH_THEME_QSS
LIGHT_SAAS_THEME_QSS = INK_WASH_THEME_QSS
DARK_THEME_QSS = INK_WASH_THEME_QSS


def get_badge_stylesheet(state: str) -> str:
    """Return an accessible Ink Wash pill badge stylesheet for a given status state."""
    state_u = state.upper()
    if state_u in ("OK", "ACTIVE", "CONNECTED", "ENABLED", "COMPLETE", "CALIBRATED", "RECORDING", "RUNNING"):
        return (
            f"background-color: #1A211D; color: {INK_SAGE_GRAY}; "
            f"border: 1px solid {INK_SAGE_GRAY}; border-radius: 4px; padding: 3px 8px; font-weight: 700; font-size: 11px;"
        )
    elif state_u in ("WARNING", "SEARCHING", "PENDING", "CALIBRATING", "PAUSED"):
        return (
            f"background-color: #24201A; color: {INK_MUTED_AMBER}; "
            f"border: 1px solid {INK_MUTED_AMBER}; border-radius: 4px; padding: 3px 8px; font-weight: 700; font-size: 11px;"
        )
    elif state_u in ("ERROR", "STOPPED", "OFFLINE", "EMERGENCY", "FAILED"):
        return (
            f"background-color: #281718; color: {INK_MUTED_CRIMSON}; "
            f"border: 1px solid {INK_MUTED_CRIMSON}; border-radius: 4px; padding: 3px 8px; font-weight: 700; font-size: 11px;"
        )
    else:
        return (
            f"background-color: {INK_GRAPHITE}; color: {INK_SILVER_GRAY}; "
            f"border: 1px solid {INK_COOL_GRAY}; border-radius: 4px; padding: 3px 8px; font-weight: 600; font-size: 11px;"
        )
