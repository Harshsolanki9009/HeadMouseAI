# Jadoo Windows Release Report

> **Release Version**: 2.0.0 (Codename: *Ink Wash & Autonomous Desktop*)  
> **Release Date**: 2026-11-24  
> **Repository**: [https://github.com/Harshsolanki9009/HeadMouseAI](https://github.com/Harshsolanki9009/HeadMouseAI)  
> **Target OS**: Windows 10 / Windows 11 x64 (Build 19045 or higher)  
> **Minimum Hardware**: Intel Core i3-6100 (2C/4T @ 3.7 GHz), 8 GB RAM, Intel HD Graphics 530 (No CUDA GPU required).

---

## 1. Release Binaries & Distribution Assets

| Asset Name | Format | Size | SHA-256 Checksum | Description |
|---|---|---|---|---|
| **`Jadoo-Setup.exe`** | Windows Inno Setup Installer | **300.5 MB** | `A48A22DD210A51FF2AE22C94223449E38D5F0854192CF7A10FF0B21E712B6E32` | Standard Windows wizard installer with desktop shortcut, Start Menu entries, and uninstaller. |
| **`Jadoo-Portable.zip`** | Portable ZIP Archive | **365.4 MB** | `CDDDDD04EB88AAE16C97BC7A1630AC242AC64E5BF8A48A122C0ECB9072331906` | Self-contained zero-install archive. Extract anywhere and launch `Jadoo.exe` without admin privileges. |

---

## 2. Bundled Subsystems & Capabilities

Every package is 100% self-contained and pre-configured for offline and hybrid execution:

1. **Face & Nose Tracking Subsystem**:
   - Pre-bundled MediaPipe Face Landmarker task model (`assets/models/face_landmarker.task`).
   - 60 FPS nose-tip cursor navigation with dead-zone noise filtering and eye-wink click stabilization.
2. **Hybrid Voice Engine**:
   - Native AVX2-accelerated `whisper.cpp` engine (`assets/bin/whisper/`) with multilingual weights (`ggml-base.bin`, `ggml-tiny.bin`).
   - Groq Cloud Whisper API client (`whisper-large-v3-turbo`) with automatic offline fallback.
   - Manual language selector (English, Hindi, Hinglish, Auto).
3. **Autonomous Desktop Task Agent**:
   - Native Win32 Vercel Labs `agent-desktop` automation binary (`assets/bin/agent-desktop/agent-desktop.exe`).
   - Qualified UIA inspection (`@ref`), visible cursor movement, natural language planning (Gemini Flash), and closed-loop execution verification.
4. **Always-on-Top Floating Control Panel**:
   - 17 large-target accessible buttons (>= 44px height).
   - Strict operating mode isolation (`DICTATION_MODE` vs `COMMAND_MODE`).
   - F9 instant emergency stop interlock.
5. **Ink Wash Design System**:
   - High-contrast monochrome palette (`#17191C`, `#222529`, `#F2F0EA`, `#B9C0C7`).
   - 7 vector SVG graphics (`assets/graphics/`).
   - Low-latency 20 FPS breathing animation timer with `reduce_motion` accessibility toggle.

---

## 3. Verification & Quality Assurance

- **Unit & Integration Suite**: 330 / 330 tests passed (`pytest-9.2.0`).
- **Real Desktop Acceptance Test**: Physical Notepad launch, typing `"Hello from Jadoo"`, Save As dialog navigation, and verification of file output on Desktop passed without mock shortcuts.
- **Resource Footprint**: Baseline memory 143.7 MB RSS; cursor calculation latency 2.66 µs / frame; memory leak growth < 1.2 MB after 1,000 continuous frames.
- **Security Audit**: Zero hardcoded API keys; `.gitignore` strictly protects `.env` credentials; F9 emergency stop verified to immediately release held inputs.

---

## 4. Installation & Quick Start

### Option A: Windows Installer
1. Download `Jadoo-Setup.exe` from GitHub Releases.
2. Double-click to launch the installer and follow the setup wizard.
3. Launch **Jadoo** from your Desktop or Start Menu.

### Option B: Portable Version
1. Download `Jadoo-Portable.zip`.
2. Extract the archive to any folder (e.g., `C:\Jadoo`).
3. Double-click `Jadoo.exe` to run immediately.

### Optional Cloud Features
If you wish to use Cloud Whisper or Gemini desktop task planning:
1. Copy `.env.example` to `.env` in the application folder (or set Windows User Environment Variables).
2. Enter your `GROQ_API_KEY` and/or `GEMINI_API_KEY`.
3. Restart Jadoo.
