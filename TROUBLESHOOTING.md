# Jadoo — Troubleshooting & Diagnostic Guide

Solutions to common issues encountered when setting up or using Jadoo on Windows.

---

## 1. Camera & Tracking Issues

### Symptom: Camera preview is black or fails to initialize
- **Fix 1: Check Windows Camera Privacy Settings**
  1. Open Windows **Settings** (`Win + I`) -> **Privacy & Security** -> **Camera**.
  2. Ensure **Camera access** is set to **On**.
  3. Ensure **Let desktop apps access your camera** is enabled.
- **Fix 2: Select Correct Camera Index**
  1. Navigate to the **Settings** tab in Jadoo.
  2. In the Camera dropdown, cycle from Index `0` to Index `1` or `2` (if you have multiple webcams or virtual cameras like OBS/Iriun installed).
- **Fix 3: Verify Lighting & Distance**
  - Sit approximately 50–70 cm away from the lens.
  - Avoid strong backlighting behind your head. Face illumination should be even.

### Symptom: Pointer drifts when head is still
- **Fix 1: Recalibrate Neutral Center**
  - Sit in a comfortable resting posture looking directly at the center of the monitor.
  - Press **`C`** on your keyboard (or click **Calibrate** in Jadoo) to re-center.
- **Fix 2: Adjust Dead Zone Setting**
  - Go to **Settings** -> **Nose Tracking**.
  - Increase the **Dead Zone** slider from `4.0 px` to `6.0 px` or `8.0 px` to eliminate resting head micro-tremors.

---

## 2. Voice & Speech Recognition Issues

### Symptom: Background fan / AC hum triggers recording
- **Fix**:
  - Jadoo includes a 100 Hz high-pass filter and adaptive RMS energy gating.
  - Go to **Settings** -> **Voice Engine**.
  - Increase the **Energy Threshold** slider slightly (e.g., from `0.035` to `0.045`).
  - Set **VAD Sensitivity** to `Medium` or `Low`.

### Symptom: "API KEY MISSING" or switches to Local Whisper
- **Cause**: Groq Cloud Whisper API key is missing or invalid.
- **Fix**:
  1. Verify your key exists at [https://console.groq.com/keys](https://console.groq.com/keys).
  2. Set the Windows environment variable:
     ```powershell
     [System.Environment]::SetEnvironmentVariable("GROQ_API_KEY", "gsk_...", "User")
     ```
  3. Or copy `.env.example` to `.env` in the Jadoo folder and add `GROQ_API_KEY=gsk_...`.
  4. Note: Jadoo continues to work 100% offline using `whisper.cpp` automatically.

---

## 3. Desktop Automation (Task Agent) Issues

### Symptom: File saved to OneDrive Desktop instead of local Desktop
- **Explanation**:
  - Windows systems with OneDrive backup automatically redirect the user's Desktop to `C:\Users\<User>\OneDrive\Desktop`.
  - Jadoo's `AgentDesktopAdapter.get_desktop_directory()` dynamically inspects Windows Registry user shell folders to target the true physical desktop directory.

### Symptom: Task agent action paused or requires approval
- **Explanation**:
  - For safety, file deletions, system registry edits, and critical commands prompt for explicit user confirmation.
  - Press the **Approve** button on the Task Agent card or speak `"approve"` to proceed.

---

## 4. Emergency Failsafe Recovery

### Symptom: Real mouse control is locked or unresponsive
- **Action**:
  - Press **`F9`** (or **`E`**) at any time.
  - F9 instantly releases all held mouse buttons, stops cursor movement, disarms actuation, and aborts any active task agent operations.
  - To resume normal operation, press **`F8`** to re-arm the mouse.
