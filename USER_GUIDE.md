# HeadMouseAI — User Guide & Manual

Welcome to **HeadMouseAI**, an AI-powered desktop application that gives you complete hands-free control of your Windows operating system using facial tracking.

---

## Table of Contents
1. [System Requirements](#1-system-requirements)
2. [Installation & First Launch](#2-installation--first-launch)
3. [Recommended Camera Setup](#3-recommended-camera-setup)
4. [Step-by-Step Calibration](#4-step-by-step-calibration)
5. [Everyday Mouse Navigation & Gestures](#5-everyday-mouse-navigation--gestures)
6. [Safety Controls & Emergency Stop](#6-safety-controls--emergency-stop)
7. [Personalizing Settings & Profiles](#7-personalizing-settings--profiles)
8. [Troubleshooting Guide](#8-troubleshooting-guide)

---

## 1. System Requirements

- **Operating System**: Windows 10 (64-bit, version 19041 or higher) or Windows 11.
- **CPU**: Intel Core i3 / AMD Ryzen 3 (or equivalent dual-core $2.0\text{ GHz}$) minimum; Intel Core i5 / AMD Ryzen 5 recommended.
- **RAM**: $4\text{ GB}$ minimum ($8\text{ GB}$ recommended).
- **Camera**: Standard USB webcam supporting $640\times 480$ at $30\text{ FPS}$ (or smartphone webcam connected via USB/Wi-Fi using Iriun Webcam or DroidCam).
- **Disk Space**: Approximately $500\text{ MB}$ free drive space for installation.

---

## 2. Installation & First Launch

### Using the Installer (Recommended)
1. Run `HeadMouseAI_Setup.exe`.
2. Follow the setup wizard prompts. By default, HeadMouseAI installs to `C:\Program Files\HeadMouseAI`.
3. Select whether to create a Desktop Shortcut.
4. Click **Install**.
5. Once complete, check **Launch HeadMouseAI** and click **Finish**.

### Using the Standalone Portable Edition
1. Extract `HeadMouseAI_Portable.zip` into any folder.
2. Double-click `HeadMouseAI.exe`. No installation or administrative privileges required.

### The First-Launch Welcome Screen
On your first launch, HeadMouseAI presents a clean onboarding dialog that explains camera positioning, hardware mouse activation, and the emergency stop hotkey. You can choose to launch the guided calibration immediately or explore the dashboard first.

---

## 3. Recommended Camera Setup

For the highest accuracy and least neck fatigue:

1. **Height & Angle**: Mount your webcam directly at eye level (on top of your primary display). Looking slightly down or straight ahead is optimal.
2. **Distance**: Sit between **50 cm and 70 cm** (roughly arm's length) from your webcam.
3. **Lighting**: Ensure even, frontal lighting on your face. Avoid strong backlighting (such as sitting directly in front of an open window), which casts facial features into shadow.
4. **Framing**: Keep your head roughly centered in the video preview box. The live preview will indicate whether your distance is optimal.

---

## 4. Step-by-Step Calibration

Calibration takes under 20 seconds and tailors HeadMouseAI to your unique resting facial structure:

### Launching Calibration
- Click the **Calibrate [C]** button on the bottom control bar, or press the **`[C]`** key on your keyboard.

### Step 1: Position Yourself
- Look at the camera preview.
- Ensure your head is centered and comfortably upright.
- Verify that the status badge indicates **OPTIMAL DISTANCE**.

### Step 2: Neutral Head Position
- Click **Start Head Calibration**.
- A 3-second animated countdown will begin.
- Simply look naturally at the center of your screen with a relaxed head posture.
- HeadMouseAI records your neutral nose coordinate center.

### Step 3: Eye Wink Controls
- Click **Start Eye Calibration**.
- Perform a natural wink with your left eye, followed by your right eye.
- The system determines your open-eye baseline and closure thresholds while automatically setting natural blink suppression filters.

### Step 4: Optional Gestures
- Calibrate eyebrow elevation (for page scrolling) and subtle smile width (for zooming).
- You may skip this step if you only wish to use head motion and clicking.

### Step 5: Confirmation & Profile Save
- Review your calibrated center and sensitivity baselines.
- Click **Save & Apply Profile**. The settings take effect immediately.

---

## 5. Everyday Mouse Navigation & Gestures

### 1. Pointer Movement
- Gently point your nose toward where you want the cursor to move on your screen.
- **Resting Dead Zone**: When your head is at rest within the neutral zone, micro-tremors are filtered out, keeping the cursor steady.
- **Smoothing**: Kalman filtering removes video noise and produces a smooth cursor path.

### 2. Left Click
- Perform a quick wink with your **left eye** (duration between $40\text{ ms}$ and $650\text{ ms}$).
- Exactly one left mouse click will be registered.
- **Click Stabilization**: During the wink, cursor movement freezes for a split second so your cursor doesn't drift away from the target button or link.

### 3. Right Click
- Perform a quick wink with your **right eye**.
- Exactly one right mouse click will be registered.

### 4. Natural Blinking (Accidental Click Prevention)
- Normal, bilateral blinking (both eyes closing together) is filtered by **Simultaneous Blink Suppression**. You can blink naturally without triggering clicks.

### 5. Hands-Free Drag & Drop
- Move your pointer over the window titlebar, icon, or file you wish to drag.
- Close your left eye and **hold it closed for $>0.38\text{ seconds}$**.
- The left mouse button engages (drag lock). The top banner will display `Dragging Active`.
- Move your head to drag the item to the desired location.
- Perform a quick wink with your left eye to release and drop the item.

### 6. Eyebrow Scroll Mode
- Raise your eyebrows and hold them raised for $>0.3\text{ seconds}$.
- Tilt your head slightly **UP** to scroll up, or **DOWN** to scroll down.
- Lower your eyebrows to resting position to stop scrolling.

### 7. Smile Zoom Mode
- Form a subtle smile (showing teeth).
- Tilt your head **UP** to zoom in, or **DOWN** to zoom out.
- Relax your mouth to return to normal cursor tracking.

---

## 6. Safety Controls & Emergency Stop

HeadMouseAI is built with fail-safe principles to guarantee the user remains in complete control:

| Safety Mechanism | Key / Trigger | Behavior |
| :--- | :---: | :--- |
| **Real Mouse Disarmed** | Default state | Real Windows cursor control is **DISABLED by default**. The green simulated cursor moves on screen for visual feedback, but your physical mouse remains untouched until explicitly armed. |
| **Toggle Real Mouse** | **`[F8]`** or **`[M]`** | Toggles real hardware mouse injection on/off. |
| **Instant Emergency Stop** | **`[F9]`** or **`[E]`** | **Immediate hardware killswitch**. Instantly disarms mouse injection, cancels any active drag, and freezes simulated movement. Requires pressing `F8` to re-arm. |
| **Face-Loss Auto-Freeze** | Automatic | If you turn your head away, look down, or step away from the webcam, mouse control halts instantly. Cursor movement resumes only when your face is re-acquired. |

---

## 7. Personalizing Settings & Profiles

Click the **Settings** tab at the top of the window to customize your experience across 6 clear categories:

1. **Camera Settings**: Switch camera devices, adjust target FPS ($15–60$), and pick video resolution.
2. **Cursor Sensitivity**:
   - *Sensitivity ($0.5–10.0$)*: Higher values require smaller head movements to reach screen edges.
   - *Dead Zone ($1.0–20.0\text{ px}$)*: Increase if you experience involuntary head shaking.
   - *Smoothing Factor ($0.0–0.9$)*: Higher values produce smoother but slightly slower response.
3. **Eye Gestures**: Adjust left/right wink sensitivity sliders and drag hold duration.
4. **Scroll & Zoom**: Tune scroll speed multiplier and zoom sensitivity.
5. **Performance**: Choose between *Balanced*, *Performance*, and *Quality* modes.
6. **Profiles**: Save configurations under user profiles (e.g., "Productivity", "Relaxed Browsing", "High Sensitivity").

---

## 8. Troubleshooting Guide

### Camera Preview is Black or Shows "Camera Unavailable"
- Ensure another application (e.g., Zoom, Teams, Skype, or Windows Camera app) is not currently locking the webcam.
- In HeadMouseAI **Settings**, change the **Camera Index** dropdown from `0` to `1` or `2`.
- Check Windows Privacy Settings: *Settings > Privacy & Security > Camera* and ensure "Let desktop apps access your camera" is **On**.

### Cursor Drifts or Jitters When Sitting Still
- Your resting dead zone may be too small for your natural posture. Go to **Settings > Cursor Sensitivity** and increase the **Dead Zone** slider to `6.0` or `8.0`.
- Re-run calibration by pressing **`[C]`** while looking naturally at the screen center.

### Winks are Not Registering
- Increase the **Wink Sensitivity** slider in **Settings > Eye Gestures**.
- Check room lighting: ensure your eyes are not obscured by heavy shadows or glare on eyeglass lenses.
- If wearing glasses, tilt your webcam slightly downward to eliminate reflection hotspots.

### Natural Blinking Triggers Accidental Clicks
- In **Settings > Eye Gestures**, lower the **Wink Sensitivity** slider slightly.
- Verify that **Simultaneous Blink Suppression** is checked in settings.

### Real Mouse Does Not Move
- Remember: Real mouse control is **DISABLED by default** upon launching the application.
- Press **`[F8]`** or click **Enable Real Mouse** on the bottom control bar. The status indicator will turn green and display `MOUSE ON`.
