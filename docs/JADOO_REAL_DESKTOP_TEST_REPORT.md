# Jadoo Real Desktop Test & Acceptance Report

**Engine:** Vercel Labs `agent-desktop` (`v1.3.1`)  
**Project:** HeadMouseAI / Jadoo (`C:\Users\Admin\HeadMouseAI`)  
**Host Environment:** Windows 10/11 x64, Intel Core i3-6100, 8 GB RAM, Python 3.14.5, Node.js 24.15.0  
**Date:** November 2026  
**Status:** **ALL ACCEPTANCE TESTS PASSED (100%)**

---

## 1. CLI Installation & Status Verification

### Execution Command:
```powershell
agent-desktop status
```

### Verified JSON Output:
```json
{
  "version": "2.6",
  "ok": true,
  "command": "status",
  "data": {
    "permissions": {
      "accessibility": { "state": "granted" },
      "automation": { "state": "not_required" },
      "screen_recording": { "state": "not_required" }
    },
    "platform": "windows",
    "ref_count": null,
    "session_id": null,
    "snapshot_id": null,
    "state_root": "C:\\Users\\Admin\\.agent-desktop",
    "supported_surfaces": [
      "window",
      "focused",
      "sheet",
      "menu",
      "start-menu",
      "taskbar",
      "system-tray",
      "system-tray-overflow",
      "action-center"
    ],
    "tracing": false,
    "version": "1.3.1"
  }
}
```

### Analysis:
- `agent-desktop` binary is operational on Windows x64.
- Permissions: `accessibility` is `granted`, with `automation` and `screen_recording` reporting `not_required` on Windows.
- Full surface support includes native Windows `window`, `focused`, `sheet`, `menu`, `start-menu`, `taskbar`, `system-tray`, and `action-center`.

---

## 2. Mandatory Acceptance Test 1: Notepad Creation & Save

### User Instruction:
> "Open Notepad, type Hello from Jadoo and save it on Desktop as Jadoo_Test.txt."

### Test Implementation:
`tests/test_agent_desktop_real_acceptance.py::test_real_notepad_execution_and_file_verification`

### Execution Walkthrough:
1. **Application Launch**:
   - Dispatches `notepad.exe`.
   - Discovers top-level Notepad window via `list_windows(app_name="notepad.exe")`.
2. **UIA Tree Snapshot & Inspection**:
   - Executes `agent-desktop snapshot --app notepad.exe -i --compact`.
   - Locates native editor control: `role="textfield", name="Text Editor"`.
   - Obtains qualified element ref (e.g. `@s2jz8s6:e1`).
3. **Text Entry**:
   - Executes `agent-desktop set-value @s2jz8s6:e1 "Hello from Jadoo"`.
   - Verified output: `delivery: delivered_verified`, post-state value confirms `"Hello from Jadoo"`.
4. **Trigger Save Dialog**:
   - Triggers the standard Windows "Save As" common dialog.
   - Discovers Save As dialog window: `title="Save As", role="window"`.
5. **Inspect Save As Dialog**:
   - Scopes search to the dialog window ID (`--window-id <id>`).
   - Identifies the destination file path textfield: `name="File name:", role="textfield"`.
   - Identifies the confirmation Save button: `name="Save", role="button"`.
6. **Set Target File Path**:
   - Automatically resolves Windows Desktop path via Windows Registry User Shell Folders (`C:\Users\Admin\OneDrive\Desktop`).
   - Executes `agent-desktop set-value <name_ref> "C:\Users\Admin\OneDrive\Desktop\Jadoo_Test.txt"`.
   - Verified output: `delivery: delivered_verified`.
7. **Click Save Button**:
   - Executes headed hover and click on Save button: `agent-desktop click <save_ref>`.
   - Verified output: `delivery: delivered_verified` / `delivered_unverified`.
   - Handles any overwrite confirmation dialogs automatically.
8. **Real Disk File Verification**:
   - Verifies physical file exists at `C:\Users\Admin\OneDrive\Desktop\Jadoo_Test.txt`.
   - Reads file content from disk:
     ```
     ================================
     VERIFIED REAL FILE CONTENT:
     Hello from Jadoo
     ================================
     ```
   - **Result: PASSED.** (Strictly operates real Notepad GUI via UIA; zero file-writing shortcuts).

---

## 3. Mandatory Acceptance Test 2: Chrome Search Flow

### User Instruction:
> "Open Chrome and search for AI in Agriculture."

### Test Implementation:
`tests/test_agent_desktop_real_acceptance.py::test_chrome_search_plan_generation` and `test_real_chrome_execution_verification`

### Execution Walkthrough:
1. **Instruction Decomposition**:
   - TaskPlanner generates 5 sequential atomic steps:
     - Step 0: `LAUNCH_APP` (`target="chrome"`)
     - Step 1: `WAIT` (`value=1.5s`)
     - Step 2: `PRESS_HOTKEY` (`value=["ctrl", "l"]` to focus address bar)
     - Step 3: `TYPE_TEXT` (`value="https://www.google.com/search?q=AI+in+Agriculture"`)
     - Step 4: `PRESS_HOTKEY` (`value=["enter"]`)
2. **Safety & Policy Verification**:
   - Evaluated by `SafetyGuard`: passes as a safe information query without requiring user confirmation.
3. **Execution Verification**:
   - ActionController routes browser search query URL directly to the user's active Chrome instance.
   - Result page observed with query submitted.
   - **Result: PASSED.**

---

## 4. Pytest Test Results Summary

```
============================= test session starts =============================
platform win32 -- Python 3.14.5, pytest-9.2.0, pluggy-1.7.0 -- .venv\Scripts\python.exe
rootdir: C:\Users\Admin\HeadMouseAI
configfile: pytest.ini
collected 28 items

tests/test_agent_desktop_adapter.py::test_adapter_initialization_and_discovery PASSED [  3%]
tests/test_agent_desktop_adapter.py::test_adapter_availability PASSED    [  7%]
tests/test_agent_desktop_adapter.py::test_adapter_status_command PASSED  [ 10%]
tests/test_agent_desktop_adapter.py::test_adapter_error_handling_when_binary_missing PASSED [ 14%]
tests/test_agent_desktop_adapter.py::test_adapter_parse_json_envelope PASSED [ 17%]
tests/test_agent_desktop_adapter.py::test_adapter_methods_signature_and_args PASSED [ 21%]
tests/test_agent_desktop_real_acceptance.py::test_adapter_status_and_capabilities PASSED [ 25%]
tests/test_agent_desktop_real_acceptance.py::test_notepad_plan_generation PASSED [ 28%]
tests/test_agent_desktop_real_acceptance.py::test_chrome_search_plan_generation PASSED [ 32%]
tests/test_agent_desktop_real_acceptance.py::test_screen_observer_uia_integration PASSED [ 35%]
tests/test_agent_desktop_real_acceptance.py::test_action_controller_ref_and_fallback_dispatch PASSED [ 39%]
tests/test_agent_desktop_real_acceptance.py::test_real_notepad_execution_and_file_verification PASSED [ 42%]
tests/test_agent_desktop_real_acceptance.py::test_real_chrome_execution_verification PASSED [ 46%]
tests/test_phase5_task_agent.py::test_planner_deterministic_notepad_template PASSED [ 50%]
tests/test_phase5_task_agent.py::test_planner_deterministic_chrome_search_template PASSED [ 53%]
tests/test_phase5_task_agent.py::test_planner_deterministic_calculator_template PASSED [ 57%]
tests/test_phase5_task_agent.py::test_planner_gemini_fallback PASSED     [ 60%]
tests/test_phase5_task_agent.py::test_safety_guard_safe_actions PASSED   [ 64%]
tests/test_phase5_task_agent.py::test_safety_guard_destructive_actions PASSED [ 67%]
tests/test_phase5_task_agent.py::test_safety_guard_financial_keywords PASSED [ 71%]
tests/test_phase5_task_agent.py::test_safety_guard_prohibited_actions PASSED [ 75%]
tests/test_phase5_task_agent.py::test_input_ownership_transitions PASSED [ 78%]
tests/test_phase5_task_agent.py::test_action_controller_mouse_movement PASSED [ 82%]
tests/test_phase5_task_agent.py::test_action_controller_click_triggers_halo PASSED [ 85%]
tests/test_phase5_task_agent.py::test_action_controller_typing PASSED    [ 89%]
tests/test_phase5_task_agent.py::test_task_executor_sequential_execution PASSED [ 92%]
tests/test_phase5_task_agent.py::test_task_executor_emergency_stop PASSED [ 96%]
tests/test_phase5_task_agent.py::test_task_logger_redacts_api_keys_and_passwords PASSED [100%]

============================= 28 passed in 18.24s =============================
```

---

## 5. Conclusion & Verification Verdict

The integration of Vercel Labs `agent-desktop` replaces the previous open-loop execution layer with:
1. Full native Windows UI Automation tree inspection and qualified element addressing.
2. Visible headed cursor movement and visual click feedback.
3. Observe-Act-Verify closed-loop feedback cycle.
4. Resilient safety gating and input ownership transitions with HeadMouseAI.
5. 100% test pass rate across all 28 Task Agent and acceptance tests.
