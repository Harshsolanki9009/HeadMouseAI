# Jadoo Phase 5: Autonomous AI Computer Task Agent

## 1. Executive Summary & Architecture

The **Jadoo Autonomous AI Computer Task Agent** empowers hands-free users to delegate multi-step desktop tasks through natural language instructions (voice or typed). Rather than performing opaque background automation, the agent operates as a **visible computer-use actor**: the user directly observes the mouse cursor smoothly traveling across the display, clicking buttons with an expanding translucent purple halo indicator, typing text naturally, and switching between active Windows applications.

```
+-----------------------------------------------------------------------------------+
|                        User Instruction (Voice or Typed UI)                       |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                           TaskPlanner (task_planner.py)                           |
|  - Fast Deterministic Templates (Notepad, Chrome Search, Calculator)              |
|  - Multimodal Gemini 2.5 Flash Decomposition for Custom Tasks                     |
|  - Pre-execution SafetyGuard Policy Annotation                                    |
+-----------------------------------------+-----------------------------------------+
                                          | produces TaskPlan
                                          v
+-----------------------------------------------------------------------------------+
|                      InputOwnershipCoordinator (input_coordinator.py)             |
|  - Transfers control: HEADMOUSE_MODE / MANUAL_MODE -> AGENT_MODE                  |
|  - Pauses HeadMouseAI tracking loop & releases held buttons (zero input conflict) |
+-----------------------------------------+-----------------------------------------+
                                          |
                                          v
+-----------------------------------------------------------------------------------+
|                       TaskExecutor Worker Thread (task_executor.py)               |
|                                                                                   |
|    +-------------------------------------------------------------------------+    |
|    |                      OBSERVE - PLAN - ACT - VERIFY                      |    |
|    |                                                                         |    |
|    |  1. OBSERVE : ScreenObserver (Active Window Title, Rect, Screenshot)    |    |
|    |  2. GUARD   : SafetyGuard (Check destructive / financial / prohibited)  |    |
|    |  3. ACT     : ActionController (Visible PyAutoGUI move, click, type)   |    |
|    |  4. VERIFY  : ScreenObserver verifies title, error state, element       |    |
|    +-------------------------------------------------------------------------+    |
|                                                                                   |
|    Emits: sig_step_started, sig_step_completed, sig_status_changed, sig_log_msg   |
+-------------------+-----------------------------------+---------------------------+
                    |                                   |
                    v                                   v
+-----------------------------------+   +-------------------------------------------+
|    ActionOverlay (action_overlay.py)   |   |     User Interfaces (Dashboard & Panel)   |
|  - Frameless Transparent Tool Win  |   |  - TaskAgentWidget (Input, Steps, Log)    |
|  - WA_TransparentForMouseEvents   |   |  - FloatingControlPanel Task Input        |
|  - Animated Expanding Purple Halo |   |  - TaskLogger (API Key / Password Redact) |
|  - Top Action Status Banner       |   |  - Emergency Stop [F9] Failsafe           |
+-----------------------------------+   +-------------------------------------------+
```

---

## 2. Core Subsystems in `task_agent/`

### 2.1 Task State & Data Structures (`task_state.py`)
- **`TaskStatus` Enum**: `PLANNING`, `WAITING_FOR_APPROVAL`, `RUNNING`, `OBSERVING`, `PAUSED`, `COMPLETED`, `FAILED`, `STOPPED`.
- **`ActionType` Enum**: `LAUNCH_APP`, `CLICK`, `DOUBLE_CLICK`, `RIGHT_CLICK`, `TYPE_TEXT`, `PRESS_HOTKEY`, `PRESS_KEY`, `SCROLL`, `WAIT`, `CAPTURE_SCREEN`, `USER_CONFIRMATION`.
- **`StepStatus` Enum**: `PENDING`, `IN_PROGRESS`, `DONE`, `FAILED`, `SKIPPED`.
- **`TaskStep` Dataclass**: Single atomic action with target string, parameter values, risk annotations, and timestamps.
- **`TaskPlan` Dataclass**: Complete execution graph for the requested instruction with serialization methods (`to_dict`, `from_dict`).

### 2.2 Input Ownership Coordinator (`input_coordinator.py`)
Guarantees strict mutual exclusivity between human input, head-mouse tracking, and autonomous agent actuation:
- **`MANUAL_MODE`**: Normal user keyboard and mouse control.
- **`HEADMOUSE_MODE`**: MediaPipe nose-tip tracking driving the OS cursor.
- **`AGENT_MODE`**: Task Agent executes visible clicks and keystrokes.
- **`PAUSED_MODE`**: All automation frozen.
- **Zero Input Clashing**: When switching to `AGENT_MODE`, `acquire_agent_ownership()` pauses `VisionWorker.mouse_controller`, releases all held buttons via `release_all_buttons()`, and preserves calibration neutral points. Once the task finishes or is halted, `release_agent_ownership(restore_headmouse=True)` returns control to the head-mouse tracking loop cleanly.

### 2.3 Transparent Click-Through Overlay (`action_overlay.py`)
Provides real-time visual feedback directly on the Windows desktop without capturing or stealing mouse clicks from target application windows:
- Configured with `Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool`.
- Enables `Qt.WidgetAttribute.WA_TransparentForMouseEvents`, allowing mouse clicks to penetrate through to background windows (e.g., Notepad, Chrome, Explorer).
- **Expanding Click Halo**: Paints an animated translucent purple ring (`#8B5CF6`) expanding outward at the exact target `(x, y)` coordinate upon each automated click.
- **Top Status Banner**: Renders current high-level action description with smooth fade-in/fade-out animations.

### 2.4 Visible Desktop Action Controller (`action_controller.py`)
Dispatches real Windows mouse movements and keystrokes using PyAutoGUI:
- **Smooth Cursor Interpolation**: Cursor moves smoothly between screen locations using easing curves (`tween=pyautogui.easeInOutQuad`, default duration `0.45s`).
- **Visible Clicks**: Calls `overlay.trigger_click_halo(x, y)` before triggering `pyautogui.click(x, y)`.
- **Typing**: Native text typing with natural character delays (`interval=0.03s`), with automatic clipboard fallback for complex multilingual Unicode strings.
- **App Launching**: Launches common Windows tools (`notepad.exe`, `chrome.exe`, `calc.exe`, `explorer.exe`, `cmd.exe`) with settling delays.

### 2.5 Task Planner (`task_planner.py`)
Decomposes natural language requests into ordered `TaskStep` chains:
1. **Fast Deterministic Templates**: Instantaneous parsing for common operations:
   - "Open Notepad and type [text]" -> Launches Notepad, waits for window focus, types text verbatim.
   - "Open Chrome and search [query]" -> Launches Chrome, focuses address bar (`Ctrl+L`), navigates to Google search URL, executes search.
   - "Open Calculator" -> Launches `calc.exe`.
2. **Gemini 2.5 Flash Fallback**: For novel, multi-step instructions, queries Gemini structured JSON output with temperature `0.2` and strict schema enforcement.
3. **Safety Annotation Pass**: Every step is evaluated by `SafetyGuard` prior to plan execution.

### 2.6 Safety Guard & Risk Policy (`safety_guard.py`)
Enforces strict boundaries against irreversible or destructive operations:
- **Safe Standard Actions**: Text typing, navigating, launching allowed applications (`ActionRiskLevel.SAFE`).
- **Destructive Operations**: File deletion (`del`, `remove`, `format`, `wipe`), directory destruction, or system modifying commands require explicit user popup authorization (`ActionRiskLevel.CONFIRMATION_REQUIRED`).
- **Financial Transactions**: Payments, checkout, credit card submission require user authorization.
- **Prohibited Exploits**: Bypassing CAPTCHAs, bot evasion, or automated payment authorizations are strictly blocked (`ActionRiskLevel.PROHIBITED`).

### 2.7 Activity Logger with Sanitization (`task_logger.py`)
Maintains an in-memory rolling buffer of actions for UI display while automatically masking sensitive data:
- Groq API keys (`gsk_...`) -> `[REDACTED_API_KEY]`
- Gemini API keys (`AIza...`) -> `[REDACTED_GEMINI_KEY]`
- Passwords (`password: ...`) -> `password: [REDACTED]`
- Credit card numbers -> `[REDACTED_CARD_NUMBER]`

---

## 3. UI Control & Monitoring Surfaces

### 3.1 Dashboard Task Agent Widget (`TaskAgentWidget`)
Integrated directly into the primary tab of `MainWindow`:
- **Natural Language Input**: Clean input bar with Enter-to-submit and "Run Task" action button.
- **Progress Checklist**: Live list widget showing each step's description with dynamic status badges (`PENDING`, `IN PROGRESS`, `DONE`, `FAILED`).
- **Control Bar**: "Pause Task", "Resume Task", and large high-contrast red "Stop Task (F9)" buttons.
- **Interactive Authorization Dialog**: Prompts user with "Authorize" / "Block" buttons when sensitive or risky steps are encountered.
- **Activity Log Viewer**: Displays sanitized, timestamped execution events in real time.

### 3.2 Floating Control Panel Integration
- Live Task Badge in header showing `IDLE`, `RUNNING`, `PAUSED`, `STOPPED`, or `COMPLETED`.
- Quick task input field in expanded view.
- "Run Task" and high-contrast "Stop Task (F9)" buttons accessible hands-free.

---

## 4. Voice Command Integration

The voice command registry supports conversational and imperative task management:
- "Start task" / "Run task" / "टास्क शुरू करो": Begins execution of the prepared plan.
- "Pause task" / "टास्क रोको": Freezes execution at current step.
- "Resume task" / "टास्क जारी रखो": Unpauses and continues remaining steps.
- "Stop task" / "Cancel task" / "टास्क बंद करो": Aborts execution and restores input control.
- "Emergency stop" / "Kill switch" / "F9": Universal halt aborting both AI cursor tracking and agent execution.

---

## 5. Verification & Test Coverage

All 15 automated test cases in `tests/test_phase5_task_agent.py` pass cleanly (100% pass rate):
1. `test_planner_deterministic_notepad_template`: Verifies Notepad step generation and text preservation.
2. `test_planner_deterministic_chrome_search_template`: Verifies Chrome search URL construction and keypresses.
3. `test_planner_deterministic_calculator_template`: Verifies Calculator launch template.
4. `test_planner_gemini_fallback`: Verifies Gemini JSON decomposition for novel tasks.
5. `test_safety_guard_safe_actions`: Verifies safe typing and waiting actions execute without prompts.
6. `test_safety_guard_destructive_actions`: Verifies file deletion commands require user confirmation.
7. `test_safety_guard_financial_keywords`: Verifies payment actions require user confirmation.
8. `test_safety_guard_prohibited_actions`: Verifies CAPTCHA bypass is strictly prohibited.
9. `test_input_ownership_transitions`: Verifies mutual exclusivity and pause/resume preservation.
10. `test_action_controller_mouse_movement`: Verifies visible PyAutoGUI smooth movement.
11. `test_action_controller_click_triggers_halo`: Verifies click coordinates trigger visual overlay halo.
12. `test_action_controller_typing`: Verifies Unicode text typing.
13. `test_task_executor_sequential_execution`: Verifies end-to-end observe-plan-act loop.
14. `test_task_executor_emergency_stop`: Verifies immediate halt upon stop request.
15. `test_task_logger_redacts_api_keys_and_passwords`: Verifies token masking in memory.
