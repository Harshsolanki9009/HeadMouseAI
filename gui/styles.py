"""Obsidian Chrome Design System Stylesheet for HeadMouseAI.

Premium Desktop Design Tokens:
- Canvas Background (Primary): #101114 (Deep Obsidian Black)
- Surface Background (Secondary): #181A1F (Refined Charcoal)
- Card & Container Background: #202226 (Obsidian Card Surface)
- Elevated Surface / Hover: #292C32 (Titanium Grey)
- Metallic Silver Accents: #A7B0BC (Muted Chrome), #C0C5CC (Silver), #E8EAED (Specular Chrome)
- Borders:
  - Base: 1px solid #2E323A (Crisp Dark Silver / Slate)
  - Subtle / Inner: 1px solid #252830
  - Hover / Active: 1px solid #3F434C
  - Focus Ring: 2px solid #A7B0BC
- Typography:
  - Primary Text: #F5F5F5 (Crisp Off-White, High Contrast)
  - Secondary Text: #A1A1AA (Zinc-400, Body / Labels)
  - Muted Text: #71717A (Zinc-500, Captions / Hints)
  - Monospace Numeral Font: "Consolas", "Cascadia Code", monospace (Tabular figures)
- Restrained State Accents:
  - Success / Active: #059669 text, #064E3B border, #022C22 background
  - Warning / Calibrating: #F59E0B text, #78350F border, #451A03 background
  - Danger / Emergency: #EF4444 text, #991B1B border, #450A0A background
"""

OBSIDIAN_CHROME_THEME_QSS = """
/* Global Window & Base Styles */
QMainWindow, QDialog, QWidget {
    background-color: #101114;
    color: #F5F5F5;
    font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Inter", "SF Pro Text", sans-serif;
    font-size: 13px;
}

/* Header Container */
QWidget#header_widget {
    background-color: #181A1F;
    border-bottom: 1px solid #2E323A;
}

/* Modern Tab Navigation */
QTabWidget::pane {
    border: 1px solid #2E323A;
    background-color: #181A1F;
    border-radius: 8px;
    top: -1px;
}

QTabBar::tab {
    background-color: #14161A;
    color: #A1A1AA;
    padding: 10px 24px;
    margin-right: 6px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-weight: 600;
    font-size: 13px;
    border: 1px solid #2E323A;
    border-bottom: none;
}

QTabBar::tab:selected {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #252830, stop:1 #1C1E24);
    color: #F5F5F5;
    border-color: #3F434C;
    border-top: 3px solid #A7B0BC;
    font-weight: 700;
}

QTabBar::tab:focus {
    outline: none;
    border-top: 3px solid #E8EAED;
    border-left: 1px solid #A7B0BC;
    border-right: 1px solid #A7B0BC;
    color: #FFFFFF;
}

QTabBar::tab:hover:!selected {
    background-color: #202226;
    color: #E4E4E7;
}

/* Cards & Group Boxes */
QGroupBox {
    background-color: #181A1F;
    border: 1px solid #2E323A;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 18px;
    padding-bottom: 12px;
    padding-left: 14px;
    padding-right: 14px;
    font-weight: 600;
    color: #F5F5F5;
    font-size: 13px;
}

QGroupBox:hover {
    border-color: #3F434C;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 3px 12px;
    background-color: #202226;
    border: 1px solid #353942;
    border-radius: 6px;
    color: #C0C5CC;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}

/* Standard Buttons */
QPushButton {
    background-color: #202226;
    color: #F5F5F5;
    border: 1px solid #353942;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 12px;
    min-height: 22px;
}

QPushButton:hover {
    background-color: #292C32;
    border-color: #4B5260;
    color: #FFFFFF;
}

QPushButton:focus {
    outline: none;
    border: 2px solid #A7B0BC;
    background-color: #292C32;
    color: #FFFFFF;
}

QPushButton:pressed {
    background-color: #181A1F;
    border-color: #2E323A;
}

QPushButton:disabled {
    background-color: #14161A;
    color: #52525B;
    border-color: #24262B;
}

/* Primary Action CTA: Start Tracking (Refined Titanium Navy Metallic Gradient) */
QPushButton#btn_start {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E3A8A, stop:1 #172554);
    border: 1px solid #3B82F6;
    color: #FFFFFF;
    font-weight: 600;
    border-radius: 6px;
    padding: 7px 18px;
}
QPushButton#btn_start:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2563EB, stop:1 #1E3A8A);
    border-color: #60A5FA;
}
QPushButton#btn_start:focus {
    outline: none;
    border: 2px solid #93C5FD;
}
QPushButton#btn_start:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E40AF, stop:1 #0F172A);
}

QPushButton#btn_stop {
    background-color: #202226;
    border: 1px solid #3F434C;
    color: #E4E4E7;
    font-weight: 600;
    border-radius: 6px;
    padding: 7px 18px;
}
QPushButton#btn_stop:hover {
    background-color: #292C32;
    border-color: #A7B0BC;
    color: #FFFFFF;
}
QPushButton#btn_stop:focus {
    outline: none;
    border: 2px solid #A7B0BC;
}

/* Mouse Control Toggle (Deep Indigo Chrome) */
QPushButton#btn_mouse_toggle {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #312E81, stop:1 #1E1B4B);
    border: 1px solid #4F46E5;
    color: #FFFFFF;
    font-weight: 600;
    border-radius: 6px;
    padding: 7px 18px;
}
QPushButton#btn_mouse_toggle:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3730A3, stop:1 #312E81);
    border-color: #6366F1;
}
QPushButton#btn_mouse_toggle:focus {
    outline: none;
    border: 2px solid #A5B4FC;
}
QPushButton#btn_mouse_toggle:pressed {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1E1B4B, stop:1 #0F0E1E);
}

/* Emergency Stop (Professional High-Visibility Dark Crimson) */
QPushButton#btn_emergency {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #991B1B, stop:1 #7F1D1D);
    border: 1px solid #DC2626;
    color: #FFFFFF;
    font-weight: 700;
    border-radius: 6px;
    padding: 7px 18px;
}
QPushButton#btn_emergency:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #B91C1C, stop:1 #991B1B);
    border-color: #EF4444;
}
QPushButton#btn_emergency:focus {
    outline: none;
    border: 2px solid #FCA5A5;
}

QPushButton#btn_calibrate {
    background-color: #202226;
    border: 1px solid #353942;
    color: #F5F5F5;
    font-weight: 600;
    border-radius: 6px;
    padding: 7px 16px;
}
QPushButton#btn_calibrate:hover {
    background-color: #292C32;
    border-color: #A7B0BC;
    color: #FFFFFF;
}
QPushButton#btn_calibrate:focus {
    outline: none;
    border: 2px solid #A7B0BC;
    background-color: #292C32;
    color: #FFFFFF;
}

/* Metallic Chrome Sliders */
QSlider::groove:horizontal {
    height: 6px;
    background: #14161A;
    border: 1px solid #2E323A;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1E3A8A, stop:1 #3B82F6);
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E8EAED, stop:1 #C0C5CC);
    border: 2px solid #A7B0BC;
    width: 16px;
    height: 16px;
    margin-top: -6px;
    margin-bottom: -6px;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background: #FFFFFF;
    border-color: #E8EAED;
}

QSlider:focus {
    outline: none;
}

QSlider::handle:horizontal:focus {
    background: #FFFFFF;
    border: 2px solid #38BDF8;
}

/* Combo Boxes & Dropdowns */
QComboBox {
    background-color: #202226;
    border: 1px solid #353942;
    border-radius: 6px;
    padding: 6px 12px;
    color: #F5F5F5;
    font-size: 12px;
    min-height: 22px;
}

QComboBox:hover {
    border-color: #4B5260;
    background-color: #252830;
}

QComboBox:focus {
    border: 2px solid #A7B0BC;
    outline: none;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #2E323A;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #A7B0BC;
    width: 0;
    height: 0;
    margin-right: 6px;
}

QComboBox QAbstractItemView {
    background-color: #181A1F;
    border: 1px solid #2E323A;
    selection-background-color: #292C32;
    selection-color: #FFFFFF;
    color: #F5F5F5;
    outline: none;
    padding: 4px;
    border-radius: 6px;
}

QComboBox QAbstractItemView:focus {
    border: 1px solid #A7B0BC;
}

/* Checkboxes */
QCheckBox {
    spacing: 8px;
    color: #A1A1AA;
    font-size: 12px;
    font-weight: 500;
}

QCheckBox:hover {
    color: #F5F5F5;
}

QCheckBox:focus {
    outline: none;
    color: #FFFFFF;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #3F434C;
    border-radius: 4px;
    background-color: #181A1F;
}

QCheckBox::indicator:hover {
    border-color: #A7B0BC;
    background-color: #202226;
}

QCheckBox::indicator:focus {
    border: 2px solid #A7B0BC;
}

QCheckBox::indicator:checked {
    background-color: #A7B0BC;
    border-color: #C0C5CC;
}

/* Progress Bars */
QProgressBar {
    background-color: #14161A;
    border: 1px solid #2E323A;
    border-radius: 5px;
    text-align: center;
    color: #F5F5F5;
    font-size: 11px;
    font-weight: 600;
    min-height: 14px;
}

QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #3B82F6, stop:1 #A7B0BC);
    border-radius: 4px;
}

/* Scroll Area & Bars */
QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollBar:vertical {
    border: none;
    background: #101114;
    width: 8px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #2E323A;
    min-height: 24px;
    border-radius: 4px;
}

QScrollBar::handle:vertical:hover {
    background: #3F434C;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* Status Bar */
QStatusBar {
    background-color: #14161A;
    border-top: 1px solid #2E323A;
    color: #A1A1AA;
    font-size: 12px;
    min-height: 28px;
    padding: 0 8px;
}

QStatusBar QLabel {
    color: #A1A1AA;
    font-weight: 500;
}
"""

# Aliases for backward compatibility across imports
LIGHT_SAAS_THEME_QSS = OBSIDIAN_CHROME_THEME_QSS
DARK_THEME_QSS = OBSIDIAN_CHROME_THEME_QSS
