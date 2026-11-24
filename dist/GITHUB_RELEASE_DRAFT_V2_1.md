# HeadMouseAI v2.1.0 — Autonomous AI Computer-Use Agent & Hands-Free Vision Control

HeadMouseAI v2.1.0 integrates an **Autonomous AI Computer-Use Agent** directly into the established, 60 FPS hands-free desktop control system.

Users can now either operate their Windows PC hands-free via **MediaPipe nose-tip tracking and eye-wink gestures**, or instruct the **Autonomous AI Agent** to carry out complex desktop workflows across real applications using natural language.

---

## 🚀 Key Highlights & New Capabilities

### 1. Autonomous AI Computer-Use Agent
- **Natural Language Task Execution**: Direct commands such as:
  - *"Open Notepad and type Hello from HeadMouseAI Autonomous Agent."*
  - *"Open Calculator and calculate 125 multiplied by 8."*
  - *"Open Chrome and search for Arduino ESP32."*
- **Native Windows Automation Engine**: Built-in Vercel Labs `agent-desktop` UIA tree inspection and Win32 interaction with PyAutoGUI fallback.
- **Visible Cursor Movement**: Real cursor movements with smooth easing across desktop elements, click halos, and visual keystrokes.
- **Observe-Act-Verify Loop**: Captures desktop state via `ScreenObserver`, measures active window geometry, executes actions, and confirms result visually after every step.
- **Dedicated UI Card & Live Preview**: Real-time checklist of planned execution steps, activity logs, live desktop observation thumbnail, and verification badge.

### 2. High-Performance Hands-Free Vision Control (HeadMouseAI)
- **60 FPS Nose-Tip Tracking**: Sub-millimeter cursor precision using MediaPipe Face Mesh landmark 1 (canonical nose tip, avoiding pupil/iris noise).
- **Asymmetric Wink Classification**: Independent left wink (left click) and right wink (right click) with bilateral blink suppression.
- **Hands-Free Drag & Drop**: Hold wink (>380ms) to drag, release to drop.
- **Facial Gesture Scrolling & Zooming**: Smile/teeth detection for continuous directional scrolling; eyebrow elevation for instant zoom.
- **Genuine Telemetry**: Real-time camera FPS, face detection, nose tracking, and calibration diagnostics.

### 3. Strict Input Ownership Coordinator
- **Authoritative State Machine**: 4 mutually exclusive modes:
  - `MANUAL`: Physical keyboard and mouse; automation inactive.
  - `HEAD_MOUSE`: Hands-free nose tracking owns mouse movement and click gestures.
  - `AUTONOMOUS_AI`: AI agent takes exclusive control of mouse and keyboard.
  - `PAUSED`: All automation halted.
- **Hardware Safety Release**: Automatically releases all held buttons and modifier keys before any mode transition.
- **F9 Global Emergency Stop**: Instant kill-switch stopping all autonomous and hands-free actions immediately.

### 4. Hybrid Cloud & Offline Voice Engine (Jadoo)
- **Cloud-First Speech Recognition**: Groq Cloud Whisper API (`whisper-large-v3-turbo`) with automatic offline fallback to local `whisper.cpp` (`ggml-base.bin`).
- **Multilingual Support**: English (`en`), Hindi (`hi`), Hinglish, and Auto Detect.
- **Voice Commands**: Multilingual aliases for turning mouse on/off, starting autonomous tasks, pausing, and emergency stop.

### 5. High-Contrast Ink Wash UI
- Crisp typography rendered with `Segoe UI`.
- Accessible 44px+ hit targets on the floating always-on-top HUD.
- Custom dark scrollbars and responsive 2-column layout.

---

## 📦 Downloads & Verification

| Asset | Size | Description |
|---|---|---|
| **`HeadMouseAI-Setup.exe`** | ~300 MB | Full Windows Installer with desktop shortcuts, uninstaller, and model weights |
| **`HeadMouseAI-v2.1.0-Windows-x64-Portable.zip`** | ~365 MB | Zero-install standalone portable distribution; extract and run `HeadMouseAI.exe` |

### System Requirements:
- **Operating System**: Windows 10 / Windows 11 (64-bit)
- **CPU**: Intel Core i3-6100 / AMD equivalent or higher
- **RAM**: 8 GB RAM
- **GPU**: Intel HD Graphics 530 or higher (no dedicated CUDA GPU required)
- **Camera**: Standard 720p/1080p USB or built-in webcam
- **Microphone**: Standard physical microphone
