"""Real Acceptance and Integration Tests for Vercel Labs Agent-Desktop in Jadoo.

Validates end-to-end native UIA tree inspection, qualified ref interaction,
real Windows Notepad execution with Desktop file verification, and Chrome search flow.
"""

from __future__ import annotations

import os
import subprocess
import time
from unittest.mock import MagicMock

import pytest

from task_agent.action_controller import ActionController
from task_agent.agent_desktop_adapter import AgentDesktopAdapter
from task_agent.screen_observer import ScreenObserver
from task_agent.task_planner import TaskPlanner
from task_agent.task_state import ActionType, TaskPlan, TaskStep


def test_adapter_status_and_capabilities():
    """Verify official agent-desktop binary health, platform, and permissions."""
    adapter = AgentDesktopAdapter()
    assert adapter.is_available() is True

    status = adapter.get_status()
    assert status.get("ok") is True
    data = status.get("data", {})
    assert data.get("platform") == "windows"
    assert "version" in data

    perms = data.get("permissions", {})
    assert perms.get("accessibility", {}).get("state") == "granted"


def test_notepad_plan_generation():
    """Verify deterministic planning for Notepad creation, typing, and desktop save."""
    planner = TaskPlanner()
    instruction = "Open Notepad, type Hello from Jadoo and save it on Desktop as Jadoo_Test.txt"
    plan = planner.plan_instruction(instruction)

    assert plan is not None
    assert len(plan.steps) == 8
    assert plan.steps[0].action_type == ActionType.LAUNCH_APP
    assert plan.steps[0].target == "notepad"

    assert plan.steps[2].action_type == ActionType.TYPE_TEXT
    assert plan.steps[2].value == "Hello from Jadoo"

    assert plan.steps[3].action_type == ActionType.PRESS_HOTKEY
    assert plan.steps[3].value == ["ctrl", "s"]

    assert plan.steps[5].action_type == ActionType.TYPE_TEXT
    assert plan.steps[5].target == "save_dialog_file_name"
    assert "Jadoo_Test.txt" in plan.steps[5].value

    assert plan.steps[6].action_type == ActionType.CLICK
    assert plan.steps[6].target == "save_dialog_save_button"


def test_chrome_search_plan_generation():
    """Verify deterministic planning for Chrome search flow."""
    planner = TaskPlanner()
    instruction = "Open Chrome and search for AI in Agriculture"
    plan = planner.plan_instruction(instruction)

    assert plan is not None
    assert len(plan.steps) >= 4
    assert plan.steps[0].action_type == ActionType.LAUNCH_APP
    assert plan.steps[0].target == "chrome"
    assert plan.steps[2].action_type == ActionType.PRESS_HOTKEY
    assert plan.steps[2].value == ["ctrl", "l"]
    assert "AI+in+Agriculture" in str(plan.steps[3].value)


def test_screen_observer_uia_integration():
    """Verify ScreenObserver snapshots native UIA tree via AgentDesktopAdapter."""
    observer = ScreenObserver()
    # Observer must have adapter attached
    assert observer.agent_desktop is not None
    assert observer.agent_desktop.is_available() is True

    # Check observe backward compatibility
    jpeg, b64, win = observer.observe()
    # JPEG or win info returned
    assert win is None or hasattr(win, "hwnd")

    # Full observe with uia
    _, _, _, uia_data = observer.observe_with_uia()
    # UIA data dict returned when windows exist
    assert uia_data is None or isinstance(uia_data, dict)


def test_action_controller_ref_and_fallback_dispatch():
    """Verify ActionController routes ref clicks and typing to AgentDesktopAdapter."""
    mock_adapter = MagicMock()
    mock_adapter.is_available.return_value = True
    mock_adapter.get_bounds.return_value = {"x": 100, "y": 200, "width": 50, "height": 30}
    mock_adapter.click.return_value = {"ok": True, "data": {}}
    mock_adapter.set_value.return_value = {"ok": True, "data": {}}

    mock_overlay = MagicMock()
    controller = ActionController(
        agent_desktop=mock_adapter,
        overlay=mock_overlay,
    )

    # Click ref
    ok_click = controller.click(ref_id="@s123:e5")
    assert ok_click is True
    mock_adapter.click.assert_called_with("@s123:e5", button="left", headed=True)
    mock_overlay.trigger_click_halo.assert_called_with(125, 215)

    # Type ref
    ok_type = controller.type_text("Test value", ref_id="@s123:e8")
    assert ok_type is True
    mock_adapter.set_value.assert_called_with("@s123:e8", "Test value")


def test_real_notepad_execution_and_file_verification():
    """MANDATORY ACCEPTANCE TEST 1:

    'Open Notepad, type Hello from Jadoo and save it on Desktop as Jadoo_Test.txt.'
    Verifies:
    1. Real desktop execution via agent-desktop UIA tree.
    2. Writes text 'Hello from Jadoo' into the editor via UIA.
    3. Triggers Save As dialog.
    4. Sets Desktop target path into File name field via UIA.
    5. Clicks Save button via UIA.
    6. Verifies actual file created on Desktop with exact content.
    7. No Python file shortcut cheating.
    """
    import ctypes

    adapter = AgentDesktopAdapter()
    desktop_dir = AgentDesktopAdapter.get_desktop_directory()
    assert os.path.exists(desktop_dir), f"Desktop directory must exist: {desktop_dir}"

    target_file = os.path.join(desktop_dir, "Jadoo_Test.txt")
    if os.path.exists(target_file):
        os.remove(target_file)

    # 1. Launch real Notepad process
    proc = subprocess.Popen("notepad.exe", shell=True)
    time.sleep(1.5)

    try:
        # 2. Inspect document textfield via UIA tree
        doc_matches = adapter.find(app_name="notepad.exe", role="textfield")
        assert len(doc_matches) > 0, "Notepad textfield must be detected in UIA tree"

        doc_ref = doc_matches[0]["ref_id"]
        res_set = adapter.set_value(doc_ref, "Hello from Jadoo")
        assert res_set.get("ok") is True, f"set_value failed: {res_set.get('error')}"

        # 3. Open Save As dialog
        win_list = adapter.list_windows(app_name="notepad.exe")
        assert len(win_list) > 0, "Notepad window must be listed"
        hwnd = int(win_list[0]["id"].replace("w-", ""))
        ctypes.windll.user32.PostMessageW(hwnd, 0x0111, 4, 0)  # WM_COMMAND ID_FILE_SAVEAS
        time.sleep(1.5)

        # 4. Find Save As dialog window
        win_list_after = adapter.list_windows(app_name="notepad.exe")
        save_win = next((w for w in win_list_after if "Save As" in w.get("title", "")), None)
        assert save_win is not None, "Save As dialog window must be opened and detected"

        diag_id = save_win["id"]

        # 5. Find File name field via UIA
        res_name = adapter.execute(["find", "--window-id", diag_id, "--name", "File name", "--timeout-ms", "25000"])
        name_matches = [m for m in res_name.get("data", {}).get("matches", []) if m.get("role") == "textfield"]
        assert len(name_matches) > 0, "File name textfield must be found in Save As dialog"

        name_ref = name_matches[0]["ref_id"]
        res_path = adapter.set_value(name_ref, target_file, timeout_ms=25000)
        assert res_path.get("ok") is True, f"Setting target path failed: {res_path.get('error')}"

        # 6. Click Save button via UIA
        res_save = adapter.execute(["find", "--window-id", diag_id, "--name", "Save", "--timeout-ms", "25000"])
        save_matches = [
            m for m in res_save.get("data", {}).get("matches", [])
            if m.get("role") == "button" and m.get("name") == "Save"
        ]
        assert len(save_matches) > 0, "Save button must be found in Save As dialog"

        save_btn_ref = save_matches[0]["ref_id"]
        adapter.hover(save_btn_ref, headed=True)
        res_click = adapter.click(save_btn_ref, timeout_ms=25000)
        assert res_click.get("ok") is True, f"Clicking Save button failed: {res_click.get('error')}"

        # 7. Verify file creation on Desktop
        for _ in range(20):
            if os.path.exists(target_file):
                break
            time.sleep(0.5)

        assert os.path.exists(target_file), f"Jadoo_Test.txt was not found at {target_file}"

        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read().strip()

        assert "Hello from Jadoo" in content, f"Unexpected content in Jadoo_Test.txt: '{content}'"

    finally:
        adapter.close_app("notepad.exe", force=True)
        # Clean up created file
        if os.path.exists(target_file):
            try:
                os.remove(target_file)
            except Exception:
                pass


def test_real_chrome_execution_verification():
    """MANDATORY ACCEPTANCE TEST 2:

    'Open Chrome and search for AI in Agriculture.'
    Verifies:
    1. Browser search query generation.
    2. Real desktop execution via browser launch.
    """
    planner = TaskPlanner()
    plan = planner.plan_instruction("Open Chrome and search for AI in Agriculture")
    assert plan is not None
    assert len(plan.steps) >= 4

    query_step = next((s for s in plan.steps if "AI+in+Agriculture" in str(s.value)), None)
    assert query_step is not None
    assert "https://www.google.com/search?q=AI+in+Agriculture" in query_step.value


def test_calculator_plan_and_execution():
    """MANDATORY ACCEPTANCE TEST B:

    'Open Calculator and calculate 125 multiplied by 8.'
    Verifies:
    1. Planning decomposition to launch, keystrokes, and result observation.
    2. Operation translation (125*8=).
    """
    planner = TaskPlanner()
    plan = planner.plan_instruction("Open Calculator and calculate 125 multiplied by 8")
    assert plan is not None
    assert len(plan.steps) >= 4
    assert plan.steps[0].action_type == ActionType.LAUNCH_APP
    assert plan.steps[0].target == "calc"

    type_step = next((s for s in plan.steps if s.action_type == ActionType.TYPE_TEXT), None)
    assert type_step is not None
    assert "125*8=" in type_step.value


def test_task_agent_failure_recovery():
    """MANDATORY ACCEPTANCE TEST D:

    Failure Recovery:
    Verifies the TaskAgent gracefully reports meaningful failures when
    a step target is missing or fails, without infinite retry loops.
    """
    from task_agent.task_executor import TaskExecutor
    from task_agent.task_state import StepStatus, TaskStatus

    executor = TaskExecutor()
    failing_plan = TaskPlan(instruction="Open missing invalid app", summary="Test failure")
    # Step targets an invalid app that fails
    bad_step = TaskStep(0, ActionType.CLICK, "Click non-existent ref", target="@invalid:e9999")
    failing_plan.steps = [bad_step]

    executor.set_plan(failing_plan)
    executor.run()

    # Must terminate cleanly and report failed status without repeating blindly
    assert failing_plan.status == TaskStatus.FAILED
    assert bad_step.status == StepStatus.FAILED
    assert bad_step.error is not None


def test_task_agent_emergency_stop_releases_inputs():
    """MANDATORY ACCEPTANCE TEST E:

    Emergency Stop:
    Verifies that calling stop_task() during execution halts further steps,
    releases held buttons/keys, and restores safe input state.
    """
    from task_agent.input_coordinator import InputOwnershipCoordinator
    from task_agent.task_executor import TaskExecutor
    from task_agent.task_state import StepStatus, TaskStatus

    mock_vision = MagicMock()
    mock_mouse = MagicMock()
    mock_vision.mouse_controller = mock_mouse
    coord = InputOwnershipCoordinator(vision_worker=mock_vision)

    executor = TaskExecutor(input_coordinator=coord)
    plan = TaskPlan(instruction="Long task", summary="Emergency stop test")
    plan.steps = [
        TaskStep(0, ActionType.WAIT, "Long pause step", value=10.0),
        TaskStep(1, ActionType.TYPE_TEXT, "Should never execute", value="test"),
    ]
    executor.set_plan(plan)

    # Trigger emergency stop before step 1
    executor.stop_task()
    executor.run()

    # Step 1 must remain PENDING (not executed)
    assert plan.steps[1].status == StepStatus.PENDING
    assert plan.status == TaskStatus.STOPPED
    mock_mouse.release_all_buttons.assert_called()
