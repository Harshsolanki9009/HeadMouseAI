# Jadoo Phase 3: Hands-Free Accessibility Control System — Technical Implementation

## 1. System Overview

**Jadoo Phase 3** provides a hands-free Windows accessibility control system integrated into **HeadMouseAI**. It empowers individuals with physical motor impairments or speech-first preferences to operate primary computer functions using predefined voice commands or an always-on-top floating desktop control panel.

The architecture is engineered for low-spec Windows desktop hardware:
- **Processor:** Intel Core i3-6100 (2 cores / 4 threads, 3.70 GHz, AVX2)
- **RAM:** 8 GB DDR4
- **Graphics:** Intel HD Graphics 530 (No CUDA GPU)
- **Runtime:** Python 3.14.5 x64 / PySide6 6.8.2.1

---

## 2. Strict Dictation Mode Isolation (Mandatory Architectural Rule)

To prevent accidental execution of commands while speaking naturally, the system enforces **strict mode-based routing** prior to command evaluation:

```
                            Speech Utterance
                                   │
                                   ▼
                       [Is Mode == DICTATION_MODE?]
                                   │
                  ┌────────────────┴────────────────┐
                 Yes                               No
                  │                                 │
     Check ONLY for Exit Phrase:                    ▼
       "Typing off" / "Stop typing"         Command Engine Active:
                  │                         • Normalizes text
        ┌─────────┴─────────┐               • Matches aliases
       Yes                  No              • Suppresses duplicates
        │                   │               • Dispatches actions
        ▼                   ▼               • "Typing on" -> Dictation
Switch Mode to       Inject SPEECH as
COMMAND_MODE         LITERAL TEXT
(Typing Stopped)     ("Backspace", "Clear all",
                     "Mouse off" typed as plain text)
```

### Isolation Guarantees:
1. **When Typing Mode is ON (`DICTATION_MODE`):**
   - All recognized speech is treated strictly as dictation text.
   - Command phrases like *"Backspace"*, *"Clear all"*, *"Delete word"*, *"Select all"*, *"Copy that"*, *"Paste"*, *"Press enter"*, *"New line"*, *"Tab"*, *"Scroll up"*, *"Scroll down"*, *"Mouse on"*, and *"Mouse off"* are **typed literally as text**.
   - Neither the command engine nor Gemini AI is allowed to reinterpret dictated words as actions.
   - Only the dedicated control phrase *"Typing off"* (or *"stop typing"*, *"dictation off"*, *"टाइपिंग ऑफ"*) exits dictation.
2. **When Typing Mode is OFF (`COMMAND_MODE` / `WAKE_LISTENING`):**
   - The predefined voice command engine is active.
   - *"Typing on"* activates dictation mode.
   - *"Hey Jadoo"* activates assistant mode.
   - Text editing, mouse toggles, and scrolling actions execute normally.
3. **Safety Interlock:**
   - **F9 Emergency Stop** and voice *"Emergency stop"* / *"Stop all"* remain active and responsive across all modes.

---

## 3. Predefined Voice Command Reference

All voice commands are processed locally after Whisper STT transcription. The engine normalizes case, removes punctuation (including Hindi danda `।`), applies Unicode NFKC normalization, and handles English, Hindi, and Hinglish variants.

| Canonical Command | Category | English Triggers | Hindi / Hinglish Triggers | Action Executed |
| :--- | :--- | :--- | :--- | :--- |
| `WAKE_UP` | Wake | *"Hey Jadoo"*, *"Hello Jadoo"*, *"Jadoo wake up"* | *"सुनो जादू"*, *"हे जादू"*, *"नमस्ते जादू"* | Activates assistant query mode |
| `TYPING_ON` | Dictation | *"Typing on"*, *"Start typing"*, *"Dictation on"* | *"टाइपिंग ऑन"*, *"टाइपिंग शुरू"*, *"डिक्टेशन शुरू"* | Switches to `DICTATION_MODE` |
| `TYPING_OFF` | Dictation | *"Typing off"*, *"Stop typing"*, *"Dictation off"* | *"टाइपिंग ऑफ"*, *"टाइपिंग बंद"*, *"डिक्टेशन बंद"* | Exits `DICTATION_MODE` -> `COMMAND_MODE` |
| `BACKSPACE` | Text Editing | *"Backspace"*, *"Press backspace"* | *"बैकस्पेस"*, *"एक अक्षर हटाओ"* | Presses Backspace |
| `DELETE_WORD` | Text Editing | *"Delete word"*, *"Delete last word"* | *"डिलीट वर्ड"*, *"शब्द हटाओ"* | Presses Ctrl + Backspace |
| `CLEAR_FIELD` | Text Editing | *"Clear all"*, *"Clear field"*, *"Clear current field"* | *"पूरा मिटाओ"*, *"सब हटाओ"* | Safely clears field (Ctrl+A -> Backspace) |
| `SELECT_ALL` | Text Editing | *"Select all"*, *"Highlight all"* | *"सेलेक्ट ऑल"*, *"सब चुनो"* | Presses Ctrl + A |
| `COPY` | Text Editing | *"Copy that"*, *"Copy"* | *"कॉपी करो"*, *"कॉपी"* | Presses Ctrl + C |
| `PASTE` | Text Editing | *"Paste"*, *"Paste that"* | *"पेस्ट करो"*, *"पेस्ट"* | Presses Ctrl + V |
| `ENTER` | Text Editing | *"Press enter"*, *"Hit enter"* | *"एंटर"*, *"एंटर दबाओ"* | Presses Enter |
| `NEW_LINE` | Text Editing | *"New line"*, *"Next line"* | *"नई लाइन"*, *"न्यू लाइन"* | Presses Shift + Enter |
| `UNDO` | Text Editing | *"Undo"*, *"Revert"* | *"अंडू"*, *"पहले जैसा"* | Presses Ctrl + Z |
| `REDO` | Text Editing | *"Redo"* | *"रीडू"*, *"फिर से करो"* | Presses Ctrl + Y |
| `TAB` | Text Editing | *"Tab"*, *"Press tab"* | *"टैब"*, *"टैब दबाओ"* | Presses Tab |
| `MOUSE_ON` | Mouse | *"Mouse on"*, *"Enable mouse"* | *"माउस ऑन"*, *"माउस चालू"* | Enables real Windows cursor control |
| `MOUSE_OFF` | Mouse | *"Mouse off"*, *"Disable mouse"* | *"माउस ऑफ"*, *"माउस बंद"* | Disables real Windows cursor control |
| `SCROLL_UP` | Mouse | *"Scroll up"*, *"Page up"* | *"स्क्रॉल अप"*, *"ऊपर स्क्रॉल"* | Scrolls active window up (+120) |
| `SCROLL_DOWN` | Mouse | *"Scroll down"*, *"Page down"* | *"स्क्रॉल डाउन"*, *"नीचे स्क्रॉल"* | Scrolls active window down (-120) |
| `RECENTER` | Mouse | *"Recenter"*, *"Center cursor"* | *"रीसेंटर"*, *"सेंटर"* | Recenters cursor tracking baseline |
| `STOP_ALL` | Safety | *"Stop all"*, *"Stop Jadoo"*, *"Stop everything"* | *"सब रोको"*, *"जादू रुको"* | Releases held buttons & stops mouse |
| `EMERGENCY_STOP`| Safety | *"Emergency stop"*, *"Emergency halt"* | *"इमरजेंसी स्टॉप"*, *"आपातकालीन रोक"* | F9 Emergency Stop |

---

## 4. Module Architecture & Implementation

### 4.1 Command Registry (`voice_engine/command_registry.py`)
- Defines canonical `AccessibilityCommand` enum and `CommandCategory` grouping.
- Maintains comprehensive English, Hindi Devanagari, and Hinglish alias lookup dictionaries.
- Supports external customization via `config/voice_commands.toml`.

### 4.2 Command Engine (`voice_engine/command_engine.py`)
- **Normalization:** Cleans punctuation, handles NFKC Unicode, collapses whitespace.
- **Matching:** Fast exact-match lookup table + regex phrase boundary matching.
- **Cooldown & Duplicate Suppression:** Tracks `_last_command` and `_last_command_time`. Duplicate speech repetitions within cooldown (0.75s) are safely dropped. Safety commands (`EMERGENCY_STOP`, `STOP_ALL`) and mode switches (`TYPING_ON`, `TYPING_OFF`) bypass cross-command cooldown.

### 4.3 Mode Manager (`voice_engine/mode_manager.py`)
- State Machine Enums: `IDLE`, `WAKE_LISTENING`, `COMMAND_MODE`, `DICTATION_MODE`, `PROCESSING`, `STOPPED`.
- Houses `ModeRouter`, implementing the strict mode isolation pipeline.

### 4.4 Keyboard Action Controller (`voice_engine/keyboard_controller.py`)
- Dispatches OS keystrokes via `pyautogui` with safety debouncing.
- **Destructive Action Protection:** `clear_current_field()` uses `Ctrl+A` followed by `Backspace` inside the active text widget. It never issues operating-system file or directory deletion calls.

### 4.5 Always-On-Top Floating Jadoo Panel (`gui/floating_panel.py`)
- **Flags:** `Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool`.
- **Theme:** High-contrast accessible SaaS styling (`#0B0D13` background, `#181B22` button cards, `#8B5CF6` purple accent, `#EF4444` danger highlights).
- **17 Accessible Buttons:** Large touch/head-mouse targets (minimum height 44-52px).
- **Dual Display Modes:**
  - **Expanded Mode:** Full grid of 17 accessible buttons organized into Speech, Editing, Mouse, and Safety.
  - **Compact Mode:** Slim 105px horizontal floating pill featuring quick "Typing ON/OFF", "Stop All", and expand button.
- **Draggability & Persistence:** Draggable via header; coordinates (`panel_x`, `panel_y`, `panel_width`, `panel_height`) and compact state persist to `config.toml`.

### 4.6 Windows Startup Integration (`utils/windows_startup.py`)
- Manages registry key `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
- Generates command: `"<python_exe>" "<app_root>\app.py" --minimized`.
- Requires explicit user opt-in confirmation; never installs silently.

---

## 5. Verification & Test Suite Summary

The automated test suite verifies all Phase 3 functionality with zero regressions across the codebase:

```text
============================= test session starts =============================
platform win32 -- Python 3.14.5, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\Admin\HeadMouseAI
configfile: pytest.ini
collected 284 items

tests\test_blink.py ............................                         [  9%]
tests\test_calibration.py ....                                           [ 11%]
tests\test_calibration_profiles.py ............                          [ 15%]
tests\test_camera.py .                                                   [ 15%]
tests\test_click_and_drag_reliability.py ...........                     [ 19%]
tests\test_click_stabilization.py ...............                        [ 25%]
tests\test_cloud_first_voice.py ........................                 [ 33%]
tests\test_cursor_mapping.py .....                                       [ 35%]
tests\test_diagnostics.py ....                                           [ 36%]
tests\test_drag_and_scroll.py ................                           [ 42%]
tests\test_eye_tracker.py ......                                         [ 44%]
tests\test_gesture_zoom.py .......................                       [ 52%]
tests\test_jadoo_assistant.py ........................                   [ 60%]
tests\test_landmarks.py ..                                               [ 61%]
tests\test_mouse_controller.py ...............                           [ 66%]
tests\test_nose_tracker.py ...                                           [ 67%]
tests\test_performance_optimization.py .......                           [ 70%]
tests\test_phase3_accessibility.py ...................                   [ 77%]
tests\test_pyside_gui.py ...............                                 [ 82%]
tests\test_voice_accuracy_and_languages.py ......................        [ 90%]
tests\test_voice_engine.py ............................                  [100%]

============================= 284 passed in 34.82s ============================
REAL_EXIT_CODE: 0
```

---

## 6. Manual Testing & Verification Instructions

1. **Launch the Application:**
   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```
2. **Verify Floating Panel Display:**
   - The floating control panel will appear in the upper-right corner of the desktop.
   - Verify it stays on top when switching to Notepad, Chrome, or Windows Explorer.
   - Drag the header to reposition it; close the app and re-launch to verify position persistence.
   - Click the "—" button to collapse into Compact Mode; click "▢" to expand.
3. **Verify Strict Dictation Mode Isolation:**
   - Say: *"Typing on"* (or click **Typing ON**). Observe the badge turns purple (`DICTATION`).
   - Open Notepad. Speak: *"Backspace, please delete word and clear all."*
   - Verify that Notepad receives the exact text *"Backspace, please delete word and clear all."* — no deletions occur!
   - Say: *"Typing off"* (or click **Typing OFF**). Observe the badge turns green (`COMMAND`).
4. **Verify Command Mode Actions:**
   - With Notepad focused and text present, say: *"Backspace"*. Observe the last character is deleted.
   - Say: *"Select all"*, then *"Copy that"*, then *"New line"*, then *"Paste"*. Verify text operations execute.
   - Say: *"Clear all"*. Verify text inside Notepad is cleanly deleted without deleting any desktop files.
5. **Verify Mouse Control Integration:**
   - Say: *"Mouse on"* (or press F8). Verify head mouse tracking takes control of the cursor.
   - Say: *"Scroll down"*, then *"Scroll up"*. Verify window scrolls vertically.
   - Say: *"Emergency stop"* (or press F9, or click **Stop All**). Verify tracking halts instantly and buttons release.
