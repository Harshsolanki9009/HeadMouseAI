# JADOO — AI-Powered Windows Desktop Assistant & Hands-Free Accessibility System

[![Version](https://img.shields.io/badge/version-v2.0.0--release-blue.svg)](https://github.com/Harshsolanki9009/HeadMouseAI/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011%20(64--bit)-0078D6.svg)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/python-3.14.5%20%7C%203.12-3776AB.svg)](https://www.python.org/)
[![GUI Framework](https://img.shields.io/badge/GUI-PySide6%20(Qt6)-41CD52.svg)](https://www.qt.io/)
[![Computer Vision](https://img.shields.io/badge/Vision-MediaPipe%20Face%20Landmarker-FF6F00.svg)](https://developers.google.com/mediapipe)
[![Speech Recognition](https://img.shields.io/badge/STT-Groq%20Cloud%20%2B%20whisper.cpp-8A2BE2.svg)](https://groq.com)
[![Desktop Automation](https://img.shields.io/badge/Automation-Vercel%20agent--desktop-black.svg)](https://agent-browser.dev/desktop/)
[![Design System](https://img.shields.io/badge/Design-Ink%20Wash%20(WCAG%20AAA)-17191C.svg)](#ink-wash-design-system)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](LICENSE)

> **Complete Hands-Free PC Operation. Limitless Accessibility. Real Autonomous Desktop Execution.**  
> *Engineered by ACROPOLIANS for Low-Resource Windows Hardware (Intel Core i3, 8 GB RAM, Intel HD Graphics, No GPU).*

---

## ✦ What is Jadoo?

**Jadoo** is a comprehensive, hands-free Windows desktop accessibility assistant that combines on-device facial landmark tracking (**HeadMouseAI**), hybrid cloud/offline voice recognition, and real desktop application automation (**Vercel agent-desktop**).

Designed from the ground up for people with motor impairments, quadriplegia, repetitive strain injuries (RSI), or hands-busy workflows, Jadoo allows you to operate every aspect of Windows without touching a physical keyboard or mouse.

---

## ✦ Key Subsystems & Capabilities

### 1. HeadMouseAI — 60 FPS Head-Controlled Cursor & Facial Gestures
- **Nose-Tip Tracking**: Ultra-smooth cursor control using MediaPipe Face Landmarker Landmark #4, dead-zone drift filtering, and exponential moving average (EMA) smoothing.
- **Independent Eye-Wink Clicks**:
  - **Left Eye Wink** (40ms – 650ms): Dispatches standard left click.
  - **Right Eye Wink** (40ms – 650ms): Dispatches standard right click.
  - **Natural Blink Filtering**: Bilateral blinks are discarded to eliminate accidental clicking.
- **Wink Click Stabilization**: Pointer automatically freezes in place during an intentional wink for pinpoint pixel accuracy.
- **Hands-Free Drag & Drop**: Holding your left eye closed for $>0.38\text{ s}$ engages left mouse down; move your head to drag items or select text, and wink to release.
- **Hands-Free Scroll & Zoom**:
  - **Smile / Show Teeth**: Activates Scroll Mode (Head UP = Scroll Up, Head DOWN = Scroll Down).
  - **Smile + Raised Eyebrows**: Switches seamlessly to Zoom Mode (Head UP = Zoom In, Head DOWN = Zoom Out).

### 2. Hybrid Voice Engine — Cloud Whisper + Offline whisper.cpp
- **Cloud-First Recognition**: Powered by Groq Cloud Whisper API (`whisper-large-v3-turbo`) with near-instant transcription.
- **100% Offline Fallback**: Automatically falls back to local AVX2-accelerated `whisper.cpp` (`ggml-base.bin`) if internet is disconnected or API keys are absent.
- **Manual Language Selection**: Dedicated dropdown supporting **English (en)**, **Hindi (hi)**, **Hinglish (hi+en)**, and **Auto-Detect**.
- **Audio Pre-Processing**: Built-in 100 Hz high-pass IIR hum filter and adaptive energy VAD gating preventing ambient room/fan noise from triggering false transcription loops.

### 3. Autonomous AI Desktop Task Agent (Vercel agent-desktop)
- **Real Windows Automation**: Integrates the official Vercel Labs `agent-desktop@1.3.1` native Win32 automation engine.
- **UI Automation (UIA) Tree Inspection**: Scans top-level and dialog windows to assign qualified `@ref` identifiers to buttons, textfields, and menus.
- **Visible Closed-Loop Execution**: Moves the actual Windows mouse cursor, clicks verified controls, types real text, and verifies task completion after every step.
- **Natural Language Planning**: Translates high-level user instructions (e.g., *"Open Notepad, write a note, and save it to Desktop"*) into verified executable steps via Google Gemini Flash.

### 4. Always-On-Top Floating Accessibility Panel
- **Accessible Control Matrix**: 17 large-target tactile buttons ($\ge 44\text{ px}$ height) providing instant one-click access to voice typing, scrolling, clicking, and AI cursor controls.
- **Strict Operating Mode Isolation**:
  - In `DICTATION_MODE`: Speech is typed **100% verbatim as literal text**. System commands (e.g., "delete", "backspace", "close") are typed as text rather than executed.
  - Only the dedicated phrase `"typing off"` exits dictation.
- **F9 Hardware & Software Emergency Stop**: Global fail-safe instantly releasing all held buttons, disabling mouse actuation, and halting autonomous task execution.

### 5. Ink Wash Design System
- **Minimalist Monochrome Aesthetics**: Deep charcoal (`#17191C`), dark graphite (`#222529`), cool gray borders (`#34383D`), and soft ivory typography (`#F2F0EA`).
- **Extreme Contrast (WCAG AAA)**: Text-to-canvas contrast ratio exceeds **13.5:1**, providing optimal visibility in all lighting conditions.
- **Suite of 7 High-Resolution Vector SVGs**: Custom vector artwork in `assets/graphics/` representing face landmark crosshairs, audio waveforms, and automation pipelines.
- **Motion Accessibility**: Low-overhead 20 FPS breathing animation timer with full support for user-configurable **Reduce Motion**.

---

## ✦ Download & Installation

### Option 1: Official Windows Installer (Recommended)
1. Download **[`Jadoo-Setup.exe`](https://github.com/Harshsolanki9009/HeadMouseAI/releases/latest)** (300 MB).
2. Run the setup wizard to install Jadoo into your Programs directory.
3. Launch **Jadoo** from your Desktop or Start Menu.

### Option 2: Portable Zero-Install Version
1. Download **[`Jadoo-Portable.zip`](https://github.com/Harshsolanki9009/HeadMouseAI/releases/latest)** (365 MB).
2. Extract the archive to any folder (e.g. `C:\Jadoo`).
3. Double-click **`Jadoo.exe`** to launch immediately without administrative rights.

### Option 3: Developer Setup (From Source)
```powershell
# 1. Clone the repository
git clone https://github.com/Harshsolanki9009/HeadMouseAI.git
cd HeadMouseAI

# 2. Create and activate Python 3.14 / 3.12 virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Copy configuration template
copy .env.example .env

# 5. Launch Jadoo
python app.py
```

---

## ✦ Controls & Shortcuts Quick Reference

| Action | Shortcut / Trigger | Description |
|---|---|---|
| **Toggle Real Mouse** | `F8` or `M` | Arms or disarms OS mouse cursor injection (Safety: Off by default). |
| **Emergency Stop** | `F9` or `E` | Instantly halts cursor, releases all buttons, and aborts tasks. |
| **Start / Stop Dictation** | `Ctrl+Shift+D` | Toggles voice dictation mode with live breathing visualizer. |
| **Calibrate Center** | `C` | Recalibrates head neutral center and resting dead-zone baseline. |
| **Left Click** | Left Eye Wink | Winks left eye (40ms – 650ms) to trigger a physical left click. |
| **Right Click** | Right Eye Wink | Winks right eye (40ms – 650ms) to trigger a physical right click. |
| **Hold to Drag** | Left Eye Hold | Closes left eye for $>0.38\text{ s}$ to engage mouse hold; wink to release. |
| **Scroll Mode** | Smile / Show Teeth | Tilt head up to scroll up, tilt head down to scroll down. |
| **Zoom Mode** | Smile + Eyebrows | Tilt head up to zoom in, tilt head down to zoom out. |

---

## ✦ Quality Assurance & Test Verification

Jadoo features a comprehensive automated test suite with **330 passing tests** verified across 26 test suites:

- **148** Face tracking, nose mapping, eye blink, and gesture tests.
- **74** Voice engine, VAD gating, and multilingual language tests.
- **19** Hands-free accessibility and mode router isolation tests.
- **11** AI Cursor card, status badge, and control tests.
- **26** Autonomous Task Agent, action controller, and Vercel adapter tests.
- **10** Real Windows Desktop Acceptance tests (including live physical Notepad file creation and desktop verification).
- **29** PySide6 GUI and visual telemetry card tests.
- **4** Accessibility target size, WCAG contrast, and stability soak tests.

---

## ✦ Documentation Index

- **[System Architecture](docs/SYSTEM_ARCHITECTURE.md)**: Deep dive into Jadoo's multi-tier subsystem design.
- **[Design System Specification](docs/JADOO_DESIGN_SYSTEM.md)**: Complete Ink Wash tokens, typography, and SVG catalog.
- **[Performance & Soak Report](docs/JADOO_PERFORMANCE_REPORT.md)**: Latency, CPU, and memory benchmark findings.
- **[Comprehensive Test Report](docs/JADOO_FINAL_TEST_REPORT.md)**: Breakdown of all 330 passing tests.
- **[Security & Safety Policy](docs/SECURITY.md)**: Emergency stops, local processing, and data privacy.
- **[Windows Release Report](docs/JADOO_RELEASE_REPORT.md)**: Release binaries, SHA-256 hashes, and changelog.
- **[Windows Build Guide](docs/BUILD_WINDOWS.md)**: Compiling from source with PyInstaller and Inno Setup.

---

## ✦ License & Credits

Developed by **ACROPOLIANS**. Licensed under the [Apache License 2.0](LICENSE).  
*Special thanks to Google DeepMind MediaPipe, Georgi Gerganov (whisper.cpp), and Vercel Labs (agent-desktop).*
