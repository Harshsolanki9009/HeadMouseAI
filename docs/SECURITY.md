# Jadoo Security & Safety Architecture

> **Security Policy and Hands-Free Safety Standards for Jadoo + HeadMouseAI.**

---

## 1. Safety by Design: Hands-Free Accessibility Controls

Assistive desktop technology that controls physical mouse cursors and keystrokes requires rigorous failsafes to protect users from accidental or runaway actions.

### A. The F9 Emergency Stop Mechanism
- **Hardware Trigger**: Pressing `F9` (or `E`) immediately triggers an instant hardware-level safety halt.
- **Voice Trigger**: Speaking `"emergency stop"`, `"stop all"`, or `"ruk jao"` immediately activates the halt.
- **Button Trigger**: A prominent crimson accessible button on both the main dashboard and floating overlay provides an instant mouse/head-click target.
- **Execution Actions**:
  1. Releases all held mouse buttons (`left`, `right`, `middle`) immediately.
  2. Disables cursor actuation (`mouse_enabled = False`).
  3. Halts any in-flight Autonomous Task Agent loops (`stop_task()`).
  4. Flushes input queues and sets the system state to `STOPPED`.

### B. Strict Operating Mode Isolation
To prevent ambient conversations or spoken dictation from accidentally executing destructive computer commands:
- **Dictation Mode (`DICTATION_MODE`)**: Every spoken word is typed strictly as literal text. Command triggers (e.g., "close window", "backspace", "clear all") are typed verbatim without executing.
- **Exit Phrase**: Only the dedicated phrase `"typing off"` (or clicking the Stop Dictation button / shortcut `Ctrl+Shift+D`) can exit dictation mode.

---

## 2. Privacy & Data Protection

### A. Local-First Processing
- **Webcam Video**: Real-time facial landmark detection (MediaPipe Face Landmarker) processes camera frames entirely in memory on the local CPU (`assets/models/face_landmarker.task`). Video frames are **never saved to disk, never streamed over the network, and never transmitted to any third party**.
- **Offline Speech Recognition**: Local `whisper.cpp` binaries (`assets/bin/whisper/`) run 100% offline using local quantization weights (`assets/models/whisper/`).

### B. Cloud Services (Opt-In & Transparent)
- Cloud Whisper (Groq) and Desktop Assistant (Gemini) are optional features.
- Audio chunks sent to Groq are ephemeral speech snippets solely for transcription.
- No user biometric data or facial landmarks are ever transmitted to cloud APIs.

---

## 3. Autonomous Task Agent Guardrails

The Jadoo Task Agent uses Vercel `agent-desktop` to interact with Windows UI Automation (UIA):
1. **Explicit Confirmation**: High-risk actions (such as file deletion, registry edits, or app uninstalls) require explicit user approval.
2. **Path Sanitization**: Dynamic Windows path resolution inspects user shell folders safely and prevents path traversal attacks (`..`).
3. **Execution Timeouts**: All agent commands enforce strict timeouts (5s to 30s) to prevent hanging processes.
4. **Child Process Cleanup**: Subprocesses and Windows handle allocations are cleaned up deterministically upon command termination.

---

## 4. API Key & Credential Management

- Application secrets (`GROQ_API_KEY`, `GEMINI_API_KEY`) are read exclusively from user environment variables or local user configuration.
- Plaintext API keys are never written to log files (`logs/`), never hardcoded in source code, and strictly excluded from Git commits via `.gitignore`.
