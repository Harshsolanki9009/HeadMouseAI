# Jadoo — Windows Build and Packaging Guide

This document details the exact reproducible steps for building standalone executables and the official Windows installer.

---

## 1. Prerequisites

- **Host OS**: Windows 10/11 x64
- **Python**: 3.14.5 or 3.12 (64-bit) in `.venv`
- **PyInstaller**: 6.22+ (`pip install pyinstaller`)
- **Inno Setup**: Version 6.7+ (Install via `winget install --id JRSoftware.InnoSetup --source winget`)
- **Node.js**: (Optional) v20+ if updating `agent-desktop`

---

## 2. Directory Structure Verification

Ensure all native model weights and binaries exist in `assets/`:
```
assets/
├── bin/
│   ├── agent-desktop/
│   │   └── agent-desktop.exe       # Native Vercel agent-desktop Win32 binary
│   └── whisper/
│       ├── whisper-cli.exe         # AVX2 whisper.cpp binary
│       ├── whisper.dll
│       └── ggml-*.dll
├── graphics/
│   ├── jadoo_logo.svg
│   ├── ink_wash_abstract.svg
│   ├── voice_waveform.svg
│   ├── ai_cursor_art.svg
│   ├── task_workflow_art.svg
│   ├── empty_state.svg
│   └── welcome_art.svg
├── icons/
│   ├── app_icon.ico
│   └── app_icon.png
└── models/
    ├── face_landmarker.task        # MediaPipe Face Landmarker model
    └── whisper/
        ├── ggml-base.bin           # Multilingual Whisper base model
        └── ggml-tiny.bin           # Multilingual Whisper tiny model
```

---

## 3. Step 1: Build Standalone Executable with PyInstaller

Run the optimized build specification:
```powershell
.venv\Scripts\activate
pyinstaller Jadoo.spec --clean --noconfirm
```

This generates `dist/Jadoo/`:
- `dist/Jadoo/Jadoo.exe` (10.4 MB windowed launcher)
- `dist/Jadoo/_internal/` (All runtime dependencies, Qt6 plugins, and assets)

### Test the Standalone Build
Launch the executable directly from PowerShell to verify there are no missing DLLs or import errors:
```powershell
& "dist\Jadoo\Jadoo.exe"
```

---

## 4. Step 2: Create the Portable ZIP Package

To generate `dist/Jadoo-Portable.zip`:
```powershell
Compress-Archive -Path "dist/Jadoo/*" -DestinationPath "dist/Jadoo-Portable.zip" -Force
```

---

## 5. Step 3: Compile the Inno Setup Windows Installer

Use the Inno Setup 6 command-line compiler (`ISCC.exe`):
```powershell
& "C:\Users\Admin\AppData\Local\Programs\Inno Setup 6\ISCC.exe" "installer/Jadoo_Setup.iss"
```

This compiles:
- `dist/Jadoo-Setup.exe` (Self-extracting wizard installer with LZMA2 ultra compression, desktop shortcuts, and uninstaller).

---

## 6. Checksum Verification

Calculate SHA-256 hashes for both release packages:
```powershell
Get-FileHash -Path "dist/Jadoo-Setup.exe", "dist/Jadoo-Portable.zip" -Algorithm SHA256
```
