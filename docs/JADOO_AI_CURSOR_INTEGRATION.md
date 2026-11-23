# Jadoo Phase 4: AI Cursor (HeadMouseAI) Integration Architecture

## 1. Executive Summary & Architectural Overview

The **Jadoo AI Cursor Subsystem** directly integrates HeadMouseAI's computer-vision-based hands-free head-tracking mouse engine into the unified Jadoo Accessibility Suite. Rather than introducing a redundant or competing cursor tracking loop, Phase 4 strictly reuses the existing, production-proven `VisionWorker`, `MouseController`, MediaPipe Face Landmarker pipeline, and gesture state machines.

```
                      +---------------------------------------+
                      |       Physical Web Camera Stream      |
                      +-------------------+-------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |         VisionWorker (QThread)        |
                      |  - MediaPipe FaceLandmark (478 pts)   |
                      |  - NoseTracker (Tip Landmark 1)       |
                      |  - BlinkDetector (EAR click/drag)     |
                      |  - GestureZoom (Smile scroll/zoom)    |
                      +-------------------+-------------------+
                                          |
                +-------------------------+-------------------------+
                |                                                   |
                v                                                   v
+-------------------------------+               +---------------------------------------+
|  MouseController (OS Level)   |               |     Status & Telemetry Pipeline       |
|  - Real Windows OS clicks     |               |  - Camera: ONLINE / OFFLINE           |
|  - Smooth movement easing     |               |  - Face: LOCKED / SEARCHING           |
|  - Failsafe boundary check    |               |  - Nose: ACTIVE / IDLE                |
|  - Pause / Resume state       |               |  - Cursor: ACTIVE / PAUSED / STOPPED  |
+---------------+---------------+               +-------------------+-------------------+
                |                                                   |
                +-------------------------+-------------------------+
                                          |
                                          v
                +---------------------------------------------------+
                |             Unified UI & Control Surfaces         |
                |  - Main Dashboard AICursorWidget                  |
                |  - Always-On-Top FloatingControlPanel             |
                |  - Local Voice Command Engine (English + Hinglish)|
                |  - Global Hotkeys [F8] Toggle / [F9] Emergency    |
                +---------------------------------------------------+
```

---

## 2. Core Components & Subsystem Interaction

### 2.1 Reusing Existing Vision & Mouse Subsystems
- **No Duplicate Camera Pipelines**: All tracking signals derive from the single camera instance managed by `VisionWorker`. No auxiliary OpenCV video captures or competing background threads are created.
- **`MouseController` Enhancements**:
  - `is_paused: bool` flag introduced to decouple temporary pauses (such as user pause or Task Agent operation) from application configuration.
  - `pause()`: Safely unlocks cursor position, calls `release_all_buttons()`, sets `is_paused = True`, and preserves all neutral calibrations in `NoseTracker`.
  - `resume()`: Validates that the face is detected and calibration is intact before re-engaging OS pointer events.
  - `get_status()`: Surfaces live state (`enabled`, `is_paused`, `is_mouse_down`, `has_face`, `is_calibrated`, `screen_x`, `screen_y`).

### 2.2 Dedicated AI Cursor Controls in Dashboard (`AICursorWidget`)
Located directly in the primary Dashboard view of `MainWindow`, `AICursorWidget` provides accessible, high-contrast controls:
- **Status Badges**:
  - `CAM`: `ONLINE` (green) / `ERROR` (red)
  - `FACE`: `LOCKED` (blue) / `SEARCHING` (yellow)
  - `NOSE`: `ACTIVE` (purple) / `IDLE` (gray)
  - `CURSOR`: `ACTIVE` (green) / `PAUSED` (yellow) / `STOPPED` (red) / `OFF` (gray)
- **High-Contrast Action Targets**:
  - **AI Cursor ON**: Starts tracking pipeline and enables OS mouse actuation.
  - **AI Cursor OFF**: Disengages OS mouse actuation while leaving tracking telemetry visible.
  - **Pause / Resume Cursor**: Temporarily freezes cursor movement without dropping camera tracking or clearing neutral calibration.
  - **Recenter [R]**: Instantly re-zeros displacement deltas to the current resting head posture.
  - **Calibrate [C]**: Launches the guided neutral posture calibration wizard.
  - **HeadMouseAI Settings**: One-click jump to detailed gesture threshold settings.
- **Live Adjustable Sliders**:
  - **Sensitivity Slider**: 0.2x to 3.0x real-time multiplier adjustment via `VisionWorker.update_dynamic_settings({"sensitivity": val})`.
  - **Smoothing Slider**: 0.05 to 0.90 EMA gain adjustment via `VisionWorker.update_dynamic_settings({"smoothing_strength": val})`.

### 2.3 Always-On-Top Floating Panel AI Cursor Controls
The floating panel (`FloatingControlPanel`) incorporates compact accessibility controls:
- Compact mode status badge displaying `ACTIVE`, `PAUSED`, or `OFF`.
- Dedicated "Cursor ON", "Cursor OFF", "Pause Cursor", "Recenter [R]", and "Calibrate [C]" large accessible buttons.
- Full bi-directional status synchronization with the main desktop dashboard.

---

## 3. Voice Command Registry & Multilingual Recognition

Cursor control actions are integrated into Jadoo's offline voice command dictionary:

| Canonical Command | Category | English Trigger Phrases | Hindi / Hinglish Aliases |
| :--- | :--- | :--- | :--- |
| `MOUSE_ON` | `MOUSE` | "mouse on", "enable mouse", "start mouse" | "माउस ऑन", "माउस चालू करो", "माउस शुरू" |
| `MOUSE_OFF` | `MOUSE` | "mouse off", "disable mouse", "turn off mouse" | "माउस ऑफ", "माउस बंद करो", "माउस बंद" |
| `PAUSE_CURSOR` | `MOUSE` | "pause cursor", "pause mouse", "pause tracking" | "कर्सर रोको", "माउस पॉज़", "पॉज़ कर्सर" |
| `RESUME_CURSOR` | `MOUSE` | "resume cursor", "resume mouse", "unpause cursor" | "कर्सर चलाओ", "माउस शुरू करो", "रिज्यूम कर्सर" |
| `CALIBRATE_CURSOR` | `MOUSE` | "calibrate cursor", "calibrate head", "calibrate mouse" | "कर्सर कैलिब्रेट", "कैलिब्रेशन शुरू", "कैलिब्रेट" |
| `RECENTER` | `MOUSE` | "recenter", "recenter cursor", "center cursor" | "कर्सर रीसेंटर", "माउस रीसेंटर", "रीसेंटर", "सेंटर" |
| `SCROLL_UP` | `MOUSE` | "scroll up", "page up" | "ऊपर स्क्रॉल", "ऊपर चलो" |
| `SCROLL_DOWN` | `MOUSE` | "scroll down", "page down" | "नीचे स्क्रॉल", "नीचे चलो" |

---

## 4. Strict Dictation Mode Isolation

To guarantee user text entry is never corrupted:
1. **In `COMMAND_MODE`**: Transcriptions are matched against the canonical command dictionary. Spoken phrases like "mouse off" trigger `worker.set_real_mouse_enabled(False)`.
2. **In `DICTATION_MODE`**: All voice commands—including "mouse on", "mouse off", "pause cursor", and "recenter"—are **strictly injected as verbatim text** into the active focused document/input field.
3. The **only** voice phrases recognized during dictation are:
   - Dedicated exit phrase: "typing off" / "stop typing" (transitions back to `COMMAND_MODE`).
   - Universal emergency stop: "emergency stop" / "kill switch" (aborts all automation).

---

## 5. Safety Failsafes & Verification

1. **Hardware Failsafe [F9]**: Pressing `F9` immediately aborts cursor tracking, releases all held mouse buttons, disengages real mouse mode, and resets internal state machines.
2. **Screen Corner Failsafe**: Moving the cursor to any physical display corner triggers PyAutoGUI failsafe interlocks, automatically disabling mouse actuation.
3. **Face Loss Interlock**: If the user's face is momentarily occluded or lost, mouse movement freezes and any held drag buttons are safely released.
4. **Idempotent Operations**: Rapid successive calls to `enable()`, `disable()`, `pause()`, and `resume()` preserve valid internal state without desynchronization or crashes.
