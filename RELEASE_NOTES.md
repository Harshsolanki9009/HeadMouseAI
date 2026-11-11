# HeadMouseAI — Release Notes

## Version v1.0.0-beta.1 (Release Candidate 1)
**Release Date**: November 11, 2026  
**Publisher**: ACROPOLIANS  
**Tagline**: *Hands-Free Control. Limitless Possibilities.*  
**Platform**: Windows 10 / Windows 11 (64-bit)  
**Artifacts**: Standalone Windows Executable & Inno Setup Installer

---

### Highlights & Features

HeadMouseAI `v1.0.0-beta.1` is the first official release candidate of our AI-powered hands-free Windows desktop mouse controller.

#### 1. Core AI Computer Vision & Tracking
- **MediaPipe Face Landmarker**: High-efficiency on-device neural landmark detection (478 3D facial points) running at $<45\text{ ms}$ inference latency.
- **Nose Tip Pointer Mapping**: Converts natural head movement into precise, jitter-free cursor coordinates.
- **Kalman & Exponential Smoothing**: Completely eliminates camera noise and involuntary micro-tremors without introducing perceptible cursor lag.
- **Resting Dead Zone Filtering**: Anchors the cursor steadily when focusing on targets or reading.

#### 2. Eye Gestures & Click Engine
- **Independent Eye Aspect Ratio (EAR)**: Real-time evaluation of left and right eye apertures independently.
- **Wink Clicks**:
  - Left Eye Wink -> Primary Left Click.
  - Right Eye Wink -> Secondary Right Click.
- **Simultaneous Blink Suppression**: Suppresses bilateral natural blinks to eliminate accidental clicks.
- **Click Position Stabilization**: Momentarily freezes cursor coordinates during a wink to prevent targeting drift.
- **Hands-Free Drag & Drop**: Holding your left eye closed for $>0.38\text{ s}$ engages drag lock; a subsequent wink releases it.

#### 3. Hands-Free Secondary Gestures
- **Eyebrow Raise Scrolling**: Raising eyebrows activates head-tilt vertical scrolling.
- **Smile / Teeth Zooming**: A subtle smile activates head-tilt zoom magnification.

#### 4. Smart Guided Calibration
- **4-Step Calibration Wizard**: Streamlined setup capturing head neutral center, wink thresholds, and optional secondary gestures in $<20\text{ s}$.
- **Live Preview in Calibration**: Integrated live camera feed with real-time landmark feedback inside the wizard.
- **Physiological Boundary Validation**: Rejects invalid or out-of-frame samples to guarantee calibration integrity.

#### 5. Obsidian Chrome Visual Identity
- **Dark Metallic Theme**: Charcoal `#101114` and `#181A1F` surfaces with metallic silver `#A7B0BC` typography and borders.
- **Startup Splash Screen**: High-resolution 3D metallic chrome ribbon sculpture with ACROPOLIANS branding.
- **Layout Optimization**: Redesigned Dashboard cards with strict boundaries, eliminating clipping and overlaps across window sizes.
- **Tabular Numerals**: High-contrast, monospaced tabular numerals for rapid real-time telemetry display.

#### 6. Safety & Failsafe Interlocks
- **Real Mouse Disabled by Default**: Physical mouse cursor injection is strictly disarmed upon application startup.
- **Hardware Hotkey Arming (`F8` / `M`)**: Debounced global hotkeys to toggle physical mouse control.
- **Instant Emergency Stop (`F9`)**: Instant killswitch that immediately disengages mouse control and releases any active drag states.
- **Face-Loss Auto-Freeze**: Cursor navigation freezes automatically whenever the user turns away from the camera.

---

### Known Limitations (v1.0.0-beta.1)
1. Tracking requires adequate facial illumination; avoid strong backlighting.
2. Camera works best positioned directly in front at eye level.
3. Glare from thick spectacles may affect subtle eye wink detection (recalibration recommended).
4. Select active webcam index in Settings when multiple virtual or physical cameras are present.

---

### Verification Summary
- **Unit & Integration Tests**: 160 passed, 0 failed
- **Python Bytecode Compilation**: Exit Code 0 (`compileall`)
- **PyInstaller Standalone Build**: Verified working (15.71 MB EXE)
- **Inno Setup Installer**: Verified clean install and uninstall (115.62 MB Setup EXE)
