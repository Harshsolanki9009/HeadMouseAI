# Jadoo — Installation & Setup Guide

This guide covers all installation methods for Jadoo on Windows 10 and Windows 11 (64-bit).

---

## System Requirements

- **Operating System**: Windows 10 (Build 19045 or higher) / Windows 11 (64-bit)
- **Processor**: Intel Core i3-6100 (2 physical cores / 4 threads @ 3.7 GHz) or equivalent AMD processor with AVX2 instruction support.
- **Memory**: 8 GB RAM minimum (Jadoo baseline uses < 150 MB).
- **Graphics**: Intel HD Graphics 530 or better (DirectX 11 / OpenGL 3.3 support; no discrete GPU required).
- **Webcam**: Standard 720p or 1080p USB or integrated webcam (30 FPS or 60 FPS).
- **Microphone**: Standard built-in or USB microphone (16 kHz audio capture).

---

## Method 1: Windows Installer (Recommended)

The easiest way to install Jadoo with automatic desktop shortcuts and Start Menu integration.

1. Download **`Jadoo-Setup.exe`** from the [GitHub Releases page](https://github.com/Harshsolanki9009/HeadMouseAI/releases).
2. Double-click `Jadoo-Setup.exe`.
3. If Windows SmartScreen displays a warning, click **More info** -> **Run anyway**.
4. Follow the setup wizard instructions. By default, Jadoo installs to:
   ```
   C:\Users\<YourUsername>\AppData\Local\Programs\Jadoo
   ```
5. Leave **Create a desktop shortcut** checked.
6. Click **Finish** to launch Jadoo.

---

## Method 2: Portable ZIP (No Installation Required)

Ideal for shared school/work computers, USB flash drives, or systems without administrator rights.

1. Download **`Jadoo-Portable.zip`** from [GitHub Releases](https://github.com/Harshsolanki9009/HeadMouseAI/releases).
2. Right-click the ZIP archive and select **Extract All...** to a folder of your choice (e.g. `C:\Jadoo`).
3. Open the extracted folder.
4. Double-click **`Jadoo.exe`** to start immediately.
5. All settings and models are contained within the folder.

---

## Method 3: Running from Source (Developer Setup)

To develop, customize, or contribute to Jadoo:

### 1. Prerequisites
- **Python**: 3.12 or 3.14 (64-bit) with `pip` installed.
- **Git for Windows**: [https://git-scm.com/download/win](https://git-scm.com/download/win)
- **Node.js**: (Optional) v20+ if modifying `agent-desktop` CLI.

### 2. Clone and Setup Environment
```powershell
# Clone the repository
git clone https://github.com/Harshsolanki9009/HeadMouseAI.git
cd HeadMouseAI

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate

# Upgrade pip and install wheel
pip install --upgrade pip setuptools wheel

# Install all project dependencies
pip install -r requirements.txt
```

### 3. Configure API Keys (Optional)
If you wish to use Cloud Whisper (Groq) or Gemini AI task planning:
```powershell
copy .env.example .env
```
Open `.env` in Notepad and add your personal keys:
```ini
GROQ_API_KEY=gsk_your_groq_key_here
GEMINI_API_KEY=AIza_your_gemini_key_here
```

### 4. Run Jadoo
```powershell
python app.py
```

---

## Post-Installation Verification

1. When Jadoo opens, verify that the **Camera**, **Microphone**, and **Engine** indicators display green or ready on the dashboard.
2. Position yourself centered 50–70 cm in front of the webcam.
3. Click **Start Tracking** to begin facial landmark detection.
4. Press **`F8`** to arm physical mouse control when ready.
5. Press **`F9`** at any time for the instant Emergency Stop.
