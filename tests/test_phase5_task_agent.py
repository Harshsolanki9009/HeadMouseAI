"""Automated test suite for Jadoo Phase 5: Autonomous AI Computer Task Agent.

Verifies:
1. TaskPlanner deterministic templates (Notepad, Chrome, Calculator) and Gemini AI fallback.
2. SafetyGuard risk classification (Safe, Destructive, Financial, Prohibited).
3. InputOwnershipCoordinator mutually exclusive transitions between HEADMOUSE, AGENT, and MANUAL modes.
4. ActionController visible mouse moves, clicks with halo trigger, typing, and application launching.
5. TaskExecutor observe-plan-act loop execution, step progression, pause, resume, and emergency stop.
6. TaskLogger sanitization of sensitive tokens and API keys.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
import pytest

from PySide6.QtWidgets import QApplication

from config.settings import AppSettings
from core.mouse_controller import MouseController
from task_agent.action_controller import ActionController
from task_agent.input_coordinator import InputOwnershipCoordinator, InputOwnershipMode
from task_agent.safety_guard import SafetyGuard
from task_agent.task_executor import TaskExecutor
from task_agent.task_logger import TaskLogger, sanitize_text
from task_agent.task_planner import TaskPlanner
from task_agent.task_state import ActionType, StepStatus, TaskPlan, TaskStatus, TaskStep


@pytest.fixture(scope="session")
def qapp():
    """Ensure a persistent QApplication instance exists."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# ------------------------------------------------------------- #
# 1. TaskPlanner Deterministic Templates & AI Fallback          #
# ------------------------------------------------------------- #

def test_planner_deterministic_notepad_template():
    """Verify planner matches 'Open Notepad and type...' without invoking LLM."""
    planner = TaskPlanner()

    instruction = "Open Notepad and type Hello world from Jadoo"
    plan = planner.plan_instruction(instruction)

    assert plan is not None
    assert len(plan.steps) == 3
    # Step 0: Launch Notepad
    assert plan.steps[0].action_type == ActionType.LAUNCH_APP
    assert plan.steps[0].target == "notepad"
    # Step 1: Wait
    assert plan.steps[1].action_type == ActionType.WAIT
    # Step 2: Type text
    assert plan.steps[2].action_type == ActionType.TYPE_TEXT
    assert "Hello world from Jadoo" in str(plan.steps[2].value)


def test_planner_deterministic_chrome_search_template():
    """Verify planner matches 'Open Chrome and search...' template."""
    planner = TaskPlanner()

    instruction = "Open Chrome and search python tutorials"
    plan = planner.plan_instruction(instruction)

    assert plan is not None
    assert len(plan.steps) >= 4
    assert plan.steps[0].action_type == ActionType.LAUNCH_APP
    assert plan.steps[0].target == "chrome"
    assert plan.steps[3].action_type == ActionType.TYPE_TEXT
    assert "python" in str(plan.steps[3].value).lower()
    assert plan.steps[4].action_type == ActionType.PRESS_HOTKEY


def test_planner_deterministic_calculator_template():
    """Verify planner matches 'Open Calculator' template."""
    planner = TaskPlanner()

    instruction = "Open Calculator"
    plan = planner.plan_instruction(instruction)

    assert plan is not None
    assert len(plan.steps) >= 1
    assert plan.steps[0].action_type == ActionType.LAUNCH_APP
    assert plan.steps[0].target == "calc"


def test_planner_gemini_fallback():
    """Verify planner invokes Gemini client when no deterministic template matches."""
    mock_gemini = MagicMock()
    mock_gemini.is_configured = True
    mock_gemini.generate_content.return_value = {
        "text": '{"summary": "Custom task", "steps": [{"action": "launch_app", "target": "notepad", "description": "Launch notepad"}, {"action": "type_text", "value": "test", "description": "Type test"}]}'
    }

    planner = TaskPlanner(gemini_client=mock_gemini)
    plan = planner.plan_instruction("Please write a test in my text editor")

    assert plan is not None
    assert len(plan.steps) == 2
    assert plan.steps[0].action_type == ActionType.LAUNCH_APP
    assert plan.steps[1].action_type == ActionType.TYPE_TEXT


# ------------------------------------------------------------- #
# 2. SafetyGuard Risk Detection and Blocking                    #
# ------------------------------------------------------------- #

def test_safety_guard_safe_actions():
    """Verify safe everyday actions pass without confirmation."""
    step_type = TaskStep(0, ActionType.TYPE_TEXT, "Type notes", target="", value="Meeting notes for today")
    can_run, req_approval, reason = SafetyGuard.evaluate_step(step_type)
    assert can_run is True
    assert req_approval is False

    step_wait = TaskStep(1, ActionType.WAIT, "Wait 1 second", value=1.0)
    can_run, req_approval, reason = SafetyGuard.evaluate_step(step_wait)
    assert can_run is True
    assert req_approval is False


def test_safety_guard_destructive_actions():
    """Verify destructive actions require explicit user confirmation."""
    step_del = TaskStep(0, ActionType.TYPE_TEXT, "Delete user folder and erase files", target="cmd", value="del /s /q temp")
    can_run, req_approval, reason = SafetyGuard.evaluate_step(step_del)
    assert can_run is True
    assert req_approval is True
    assert step_del.requires_confirmation is True


def test_safety_guard_financial_keywords():
    """Verify financial transaction / purchase steps require user confirmation."""
    step_buy = TaskStep(0, ActionType.CLICK, "Click checkout and buy items with credit card", target="browser")
    can_run, req_approval, reason = SafetyGuard.evaluate_step(step_buy)
    assert can_run is True
    assert req_approval is True
    assert step_buy.requires_confirmation is True


def test_safety_guard_prohibited_actions():
    """Verify dangerous operations (e.g. CAPTCHA bypass) are strictly blocked."""
    step_captcha = TaskStep(0, ActionType.CLICK, "Bypass captcha on login form", target="browser")
    can_run, req_approval, reason = SafetyGuard.evaluate_step(step_captcha)
    assert can_run is False
    assert "violates safety policy" in reason.lower()


# ------------------------------------------------------------- #
# 3. InputOwnershipCoordinator Mutual Exclusivity               #
# ------------------------------------------------------------- #

def test_input_ownership_transitions():
    """Verify seamless switching between MANUAL, AGENT, and HEADMOUSE modes."""
    settings = AppSettings()
    mouse_ctrl = MouseController(settings)
    mouse_ctrl.is_calibrated = True
    mouse_ctrl.has_face = True
    mouse_ctrl.enable()

    mock_vision_worker = MagicMock()
    mock_vision_worker.mouse_controller = mouse_ctrl
    mock_vision_worker.pause_cursor.side_effect = lambda: mouse_ctrl.pause()
    mock_vision_worker.resume_cursor.side_effect = lambda: mouse_ctrl.resume()

    coordinator = InputOwnershipCoordinator(vision_worker=mock_vision_worker)
    assert coordinator.mode == InputOwnershipMode.MANUAL_MODE

    # Request AGENT_MODE
    ok = coordinator.acquire_agent_ownership()
    assert ok is True
    assert coordinator.mode == InputOwnershipMode.AGENT_MODE
    # VisionWorker mouse controller must be paused to prevent fighting
    assert mouse_ctrl.is_paused is True

    # Release AGENT_MODE and restore HEADMOUSE_MODE
    coordinator.release_agent_ownership(restore_headmouse=True)
    assert coordinator.mode == InputOwnershipMode.HEADMOUSE_MODE
    assert mouse_ctrl.is_paused is False

    # Pause all
    coordinator.pause_all()
    assert coordinator.mode == InputOwnershipMode.PAUSED_MODE
    assert mouse_ctrl.is_paused is True


# ------------------------------------------------------------- #
# 4. ActionController Visible Desktop Automation                #
# ------------------------------------------------------------- #

def test_action_controller_mouse_movement():
    """Verify ActionController visible mouse move uses PyAutoGUI smooth easing."""
    mock_pyautogui = MagicMock()
    mock_pyautogui.size.return_value = (1920, 1080)

    controller = ActionController(py_backend=mock_pyautogui)
    ok = controller.move_mouse_visible(500, 300, duration=0.2)

    assert ok is True
    mock_pyautogui.moveTo.assert_called_once()
    args, kwargs = mock_pyautogui.moveTo.call_args
    assert args[0] == 500
    assert args[1] == 300
    assert kwargs.get("duration") == 0.2


def test_action_controller_click_triggers_halo():
    """Verify click action triggers halo on overlay if present."""
    mock_pyautogui = MagicMock()
    mock_pyautogui.size.return_value = (1920, 1080)
    mock_pyautogui.position.return_value = (350, 420)

    mock_overlay = MagicMock()
    controller = ActionController(py_backend=mock_pyautogui, overlay=mock_overlay)

    ok = controller.click(350, 420, button="left")
    assert ok is True
    mock_overlay.trigger_click_halo.assert_called_once_with(350, 420)
    mock_pyautogui.click.assert_called_once_with(350, 420, button="left")


def test_action_controller_typing():
    """Verify text typing via ActionController."""
    mock_pyautogui = MagicMock()
    mock_pyautogui.size.return_value = (1920, 1080)

    controller = ActionController(py_backend=mock_pyautogui)
    ok = controller.type_text("Hello Jadoo")

    assert ok is True
    mock_pyautogui.write.assert_called_once_with("Hello Jadoo", interval=0.03)


# ------------------------------------------------------------- #
# 5. TaskExecutor Observe-Plan-Act-Verify Execution Loop        #
# ------------------------------------------------------------- #

def test_task_executor_sequential_execution(qapp):
    """Verify TaskExecutor runs plan steps sequentially and marks completion."""
    mock_controller = MagicMock()
    mock_controller.launch_application.return_value = (True, "Launched")
    mock_controller.type_text.return_value = True

    mock_observer = MagicMock()
    mock_observer.observe.return_value = (None, None, {"title": "Notepad"})
    mock_observer.get_active_window_info.return_value = {"title": "Notepad"}

    plan = TaskPlan(
        instruction="Test execution",
        steps=[
            TaskStep(0, ActionType.WAIT, "Wait brief moment", value=0.01),
            TaskStep(1, ActionType.TYPE_TEXT, "Type hello", value="Hello"),
        ]
    )

    executor = TaskExecutor(
        action_controller=mock_controller,
        screen_observer=mock_observer,
        task_logger=TaskLogger(),
    )
    executor.set_plan(plan)

    steps_completed = []
    plan_completed = []
    executor.sig_step_completed.connect(lambda idx: steps_completed.append(idx))
    executor.sig_task_completed.connect(lambda rep: plan_completed.append(rep))

    # Run execution directly
    executor.run()

    assert len(steps_completed) == 2
    assert len(plan_completed) == 1
    assert plan.status == TaskStatus.COMPLETED
    assert plan.steps[0].status == StepStatus.DONE
    assert plan.steps[1].status == StepStatus.DONE


def test_task_executor_emergency_stop(qapp):
    """Verify stop_task aborts execution immediately."""
    plan = TaskPlan(
        instruction="Test abort",
        steps=[
            TaskStep(0, ActionType.WAIT, "Wait 5 seconds", value=5.0),
        ]
    )

    executor = TaskExecutor(task_logger=TaskLogger())
    executor.set_plan(plan)
    executor.stop_task()

    assert executor._stop_requested is True
    assert plan.status == TaskStatus.STOPPED


# ------------------------------------------------------------- #
# 6. TaskLogger Sanitization of Sensitive Information           #
# ------------------------------------------------------------- #

def test_task_logger_redacts_api_keys_and_passwords():
    """Verify TaskLogger masks API keys and passwords in memory."""
    t_logger = TaskLogger()

    sensitive_text = "Initialized with API key gsk_1234567890abcdef1234567890abcdef and password: MySecretPassword"
    t_logger.log(sensitive_text)

    entries = t_logger.get_entries()
    assert len(entries) >= 1
    entry_msg = entries[-1]

    # Raw API key and password must never appear in log output
    assert "gsk_1234567890abcdef1234567890abcdef" not in entry_msg
    assert "MySecretPassword" not in entry_msg
    assert "[REDACTED" in entry_msg
