# Jadoo Autonomous Desktop Assistant: Vercel Labs Agent-Desktop Integration

**Project Root:** `C:\Users\Admin\HeadMouseAI`  
**Engine:** [Vercel Labs agent-desktop](https://github.com/vercel-labs/agent-desktop) (`v1.3.1`)  
**Platform:** Windows 10/11 x64 (UI Automation native architecture)  
**Date:** November 2026

---

## 1. Architectural Diagnosis & Motivation

### Limitations of the Previous Execution Layer
Prior to this integration, the Jadoo Task Agent relied on a combination of raw Win32 foreground rect queries (`GetForegroundWindow`) and open-loop `pyautogui` synthetic keystrokes and clicks:

1. **Blind Execution**: `ScreenObserver` only captured static JPEG screenshots and top-level window bounding boxes. It had no access to the Windows UI Automation (UIA) accessibility tree, making it impossible to inspect controls, buttons, menus, or textfields.
2. **Coordinate Guesswork & Screen Resolution Fragility**: Clicking buttons required hardcoded or guessed screen pixel coordinates. DPI scaling, window repositioning, or theme alterations broke click delivery silently.
3. **Open-Loop Planning**: The agent decomposed natural language instructions into static steps upfront. If an application took longer to settle or opened an unexpected dialog (such as a modal "Save As" window), the sequence failed.
4. **No Verification Mechanism**: Actions were marked `DONE` simply if the synthetic input call did not raise a Python exception, without verifying whether the UI state changed or whether files were written to disk.

### The Solution: Vercel Labs `agent-desktop`
Vercel Labs `agent-desktop` provides a high-reliability CLI specifically designed for AI computer use on Windows:
- Captures the live native Windows Accessibility / UI Automation tree as structured JSON with qualified, unique ref IDs (`@<snapshot_id>:e<N>`).
- Supports **headed physical pointer and keyboard interactions** (`--headed mouse-move`, `--headed hover`, `--headed mouse-click`, `--headed type`).
- Supports **direct semantic actions** (`set-value`, `click`, `select`, `toggle`, `expand`, `collapse`, `scroll`).
- Emits structured JSON response envelopes with explicit `delivery` and `retry` dispositions (`delivered_verified`, `delivered_unverified`, `not_delivered`).

---

## 2. Integration Architecture

The integration introduces a clean, multi-layered architecture within `task_agent/`:

```
┌──────────────────────────────────────────────────────────────────┐
│                     Natural Language Input                       │
│      "Open Notepad, type Hello from Jadoo and save..."           │
└─────────────────────────────────┬────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                   TaskPlanner (Gemini 2.5 Flash)                 │
│         Decomposes request into sequential TaskSteps             │
└─────────────────────────────────┬────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                     SafetyGuard Policy Engine                    │
│   Blocks prohibited exploits; flags destructive/financial actions │
└─────────────────────────────────┬────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                   InputOwnershipCoordinator                      │
│        Pauses HeadMouseAI tracking; acquires AGENT_MODE          │
└─────────────────────────────────┬────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│              TaskExecutor (Observe-Act-Verify Loop)              │
│                                                                  │
│  1. OBSERVE:                                                     │
│     ScreenObserver + AgentDesktopAdapter snapshot / find         │
│     Reads native UIA tree & qualified @ref IDs                   │
│                                                                  │
│  2. ACT:                                                         │
│     ActionController -> AgentDesktopAdapter                      │
│     - Visibly moves cursor via headed pointer input              │
│     - Displays click halo indicator overlay                      │
│     - Interacts via qualified refs (@s...:e...) or controls      │
│     - Controlled fallback to PyAutoGUI if UIA unavailable        │
│                                                                  │
│  3. VERIFY:                                                      │
│     - Re-reads live element state via get / is / snapshot        │
│     - Verifies physical file creation and content on disk        │
└─────────────────────────────────┬────────────────────────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Input Ownership Release                       │
│        Restores HeadMouseAI tracking seamlessly to user          │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Modules & Implementation Details

### A. `task_agent/agent_desktop_adapter.py`
The primary Python adapter bridge to the official binary:
- **Executable Discovery**: Automatically checks `%APPDATA%\npm\node_modules\agent-desktop\bin\agent-desktop-win32-x64.exe` (fastest direct binary call without batch script wrappers), followed by system `PATH` candidates (`agent-desktop`, `agent-desktop.cmd`).
- **Standard JSON Envelope Parsing**: Dispatches CLI commands via UTF-8 subprocess streams with configurable timeouts, robustly parsing `{"version": "2.6", "ok": true, "command": ..., "data": ...}` and extracting `disposition.delivery` and `error` structures.
- **Qualified Ref Management**: Properly handles qualified refs (`@s1y8xr5:e1`).
- **Desktop Redirection Resolution**: Includes `AgentDesktopAdapter.get_desktop_directory()` which inspects the Windows Registry (`User Shell Folders`) to resolve true desktop paths when Windows OneDrive folder backup is active (`C:\Users\Admin\OneDrive\Desktop`).
- **Resilient Fallback**: In `click()`, if headed physical delivery encounters an unfocused background window during automated test execution, it automatically falls back to native semantic UIA press action (`InvokePattern.Invoke`), guaranteeing reliable operation across both interactive and automated contexts.

### B. `task_agent/action_controller.py`
Enhanced visible desktop action dispatcher:
- **Primary UIA Dispatch**: Delegates ref clicks, element typing, and headed cursor positioning to `AgentDesktopAdapter`.
- **Visible Cursor Motion**: Visually moves the mouse pointer to element bounds centers (`bounds['x'] + bounds['width'] / 2.0`) before interacting, triggering the translucent purple click halo overlay.
- **Controlled Fallback**: PyAutoGUI is retained strictly as a coordinate-based fallback for custom, game, or non-accessible legacy windows. The two engines never compete for input ownership.

### C. `task_agent/screen_observer.py`
Augmented screen inspection:
- Provides `observe_with_uia(app_name, window_id)` returning both the visual JPEG screenshot and the full structured UIA accessibility tree.
- Retains 100% backward compatibility for existing callers through `observe() -> (jpeg_bytes, b64_str, win_info)`.

### D. `task_agent/task_executor.py` & `task_agent/task_planner.py`
Closed-loop dynamic execution:
- Decomposes tasks into atomic `TaskStep` objects.
- Inspects target window titles and UIA hierarchies dynamically at runtime.
- For document workflows (e.g. Notepad Save As), identifies dialog windows by role and title, locates input controls (`role="textfield", name="File name"`), sets values, clicks buttons, handles any overwrite confirmation prompts, and verifies that the file physically exists on disk before declaring success.

---

## 4. Safety & Input Ownership Governance

1. **Input Ownership Coordinator (`task_agent/input_coordinator.py`)**:
   - Before any agent action begins, the coordinator pauses the HeadMouseAI cursor tracking worker to prevent fighting between head tracking and agent cursor input.
   - Any held mouse buttons or keys are safely released.
   - Upon task completion, failure, or emergency stop, HeadMouseAI tracking is automatically resumed, restoring hands-free control.
2. **Emergency Stop (F9 Key)**:
   - Dedicated global keyboard hook listening for the `F9` key immediately calls `stop_task()`, terminates active agent-desktop subprocesses, and releases all inputs to manual mode.
3. **Safety Guard (`task_agent/safety_guard.py`)**:
   - Detects destructive patterns (e.g. `del`, `format`, `rmdir`) and financial transactions, pausing the task and requiring explicit user authorization via dialog before proceeding.
   - Strictly blocks prohibited exploits (CAPTCHA bypass, credential theft, unauthorized script execution).
