# JADOO — Overnight Mission Baseline Audit

**Date:** November 24, 2026 (01:40 AM IST)  
**Host Environment:** Windows 10/11 x64  
**Hardware Profile:** Intel Core i3-6100 (2C/4T @ 3.7GHz), 8 GB RAM, Intel HD Graphics 530, No CUDA GPU  
**Runtime:** Python 3.14.5 (.venv), Node.js v24.15.0, npm 12.2.0  
**Repository Remote:** `https://github.com/Harshsolanki9009/HeadMouseAI.git`  
**Base Branch:** `main`  
**Safety Checkpoint Branch:** `backup-pre-overnight-mission`

---

## 1. Application Architecture & Entry Points

- **Primary Desktop Application Entry Point:** `app.py`
  - Initializes PySide6 application with explicit Windows AppUserModelID (`HeadMouseAI.DesktopApp.1.0`).
  - Automatically loads and resolves API keys from Windows User Environment variables and local settings.
  - Displays multi-resolution application icon (`assets/icons/app_icon.ico` / `.png`).
  - Launches animated splash screen, loading configuration, camera tracking subsystems, and UI widgets before transitioning to `MainWindow`.
  - Integrates draggable always-on-top `FloatingPanel` with compact/expanded views.
- **Secondary / Legacy Entry Point:** `main.py` (legacy Tkinter/OpenCV script, retained for baseline reference).

---

## 2. Subsystems Status at Baseline

| Subsystem | Module Location | Status / Capabilities |
| :--- | :--- | :--- |
| **HeadMouseAI Vision Engine** | `core/`, `gui/worker.py` | MediaPipe face landmark detection, nose-tip cursor control, eye blink left/right clicking, smile scrolling, hold-to-drag, dynamic calibration profiles. |
| **Voice Engine** | `voice_engine/`, `ai_provider/` | Hybrid Cloud-First: Groq Cloud Whisper (`whisper-large-v3-turbo`) with automatic offline `whisper.cpp` fallback. Hindi (`hi`), English (`en`), Hinglish multilingual decoding. Energy VAD with 100Hz high-pass filter. |
| **Jadoo AI Assistant** | `jadoo_assistant/`, `ai_provider/` | Gemini 2.5 Flash assistant with screenshot/visual screen context comprehension, Windows SAPI text-to-speech feedback, conversation history. |
| **Floating Panel** | `gui/floating_panel.py` | Always-on-top, draggable, compact pill mode with microphone toggle, HeadMouse quick recenter, and expanded control mode. |
| **AI Cursor Integration** | `gui/widgets/ai_cursor_widget.py` | Single shared `VisionWorker` instance; controls sensitivity, smoothing, nose tracking telemetry without duplicate camera threads. |
| **Autonomous Task Agent** | `task_agent/` | Vercel Labs `agent-desktop` (v1.3.1) integration; native Windows UIA tree snapshots, qualified ref IDs (`@<snapshot_id>:e<N>`), headed visible mouse movements, click halos, file creation verification. |
| **Safety Governance** | `task_agent/safety_guard.py` | F9 Emergency Stop keyboard listener, destructive operation confirmation checks, strict blocking of unauthorized access/exploits. |

---

## 3. Dependency Inventory

- `PySide6`: 6.12.0 (Qt 6.12 UI framework)
- `opencv-python-headless`: 5.0.0.93 / `opencv-python`: 5.0.0.93
- `mediapipe`: 1.2.2 / `mediapipe-legacy`: 0.10.14
- `numpy`: 2.5.4
- `pyautogui`: 0.9.54
- `pyperclip`: 1.11.0
- `sounddevice`: 0.5.6
- `psutil`: 7.2.2
- `pyinstaller`: 6.22.3
- `pytest`: 9.2.0
- `agent-desktop`: 1.3.1 (global npm package with native `agent-desktop-win32-x64.exe`)

---

## 4. Initial Test Verification

- Pre-existing verified tests: 310+ tests across `test_blink.py`, `test_calibration.py`, `test_cloud_first_voice.py`, `test_voice_engine.py`, `test_phase3_accessibility.py`, `test_phase4_ai_cursor.py`, etc.
- Task Agent & Acceptance tests: 28 passing tests in `tests/test_agent_desktop_adapter.py`, `tests/test_agent_desktop_real_acceptance.py`, and `tests/test_phase5_task_agent.py`.
- Real Acceptance Test 1 (Notepad Test): Verified real GUI creation and disk save to Desktop (`Jadoo_Test.txt`) with exact content `"Hello from Jadoo"`.
- Real Acceptance Test 2 (Chrome Search Test): Verified browser launch and search query submission for `"AI in Agriculture"`.

---

## 5. Existing Packaging & Installer Configuration

- `HeadMouseAI.spec`: PyInstaller spec file for building the standalone executable bundle.
- `installer/HeadMouseAI_Setup.iss`: Inno Setup 6 script configured for building Windows installer EXE with start menu and desktop shortcuts.
- Target release outputs:
  - `dist/Jadoo-Setup.exe`
  - `dist/Jadoo-Portable.zip`
