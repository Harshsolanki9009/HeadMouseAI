"""Background Execution Worker for Jadoo Autonomous Desktop Agent.

Runs the controlled observe-plan-act-verify loop inside a dedicated QThread.
Maintains full responsiveness of the GUI while visibly executing desktop tasks.
"""

from __future__ import annotations

import ctypes
import os
import time
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot

from task_agent.action_controller import ActionController
from task_agent.action_overlay import ActionOverlay
from task_agent.agent_desktop_adapter import AgentDesktopAdapter
from task_agent.input_coordinator import InputOwnershipCoordinator
from task_agent.safety_guard import SafetyGuard
from task_agent.screen_observer import ScreenObserver
from task_agent.task_logger import TaskLogger
from task_agent.task_state import ActionType, StepStatus, TaskPlan, TaskStatus, TaskStep
from utils.logger import logger


class TaskExecutor(QThread):
    """Background worker orchestrating the sequential execution of TaskPlan steps."""

    # Outgoing Signals to UI & Coordinator
    sig_status_changed = Signal(str)             # TaskStatus value
    sig_step_started = Signal(int, str)          # (step_index, description)
    sig_step_completed = Signal(int)             # step_index
    sig_step_failed = Signal(int, str)           # (step_index, error)
    sig_confirmation_required = Signal(int, str) # (step_index, description)
    sig_task_completed = Signal(dict)            # Final report dict
    sig_log_message = Signal(str)                # Activity log entry

    def __init__(
        self,
        action_controller: Optional[ActionController] = None,
        screen_observer: Optional[ScreenObserver] = None,
        input_coordinator: Optional[InputOwnershipCoordinator] = None,
        task_logger: Optional[TaskLogger] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.action_controller = action_controller or ActionController()
        self.screen_observer = screen_observer or ScreenObserver()
        self.input_coordinator = input_coordinator
        self.task_logger = task_logger or TaskLogger()

        self.current_plan: Optional[TaskPlan] = None
        self._running: bool = False
        self._paused: bool = False
        self._stop_requested: bool = False
        self._pending_approval: bool = False
        self._step_approved: bool = False

    def set_plan(self, plan: TaskPlan) -> None:
        """Assign a new TaskPlan to be executed."""
        self.current_plan = plan

    @Slot()
    def pause_task(self) -> None:
        """Pause active task execution."""
        if self._running and not self._paused:
            self._paused = True
            if self.current_plan:
                self.current_plan.status = TaskStatus.PAUSED
            self.sig_status_changed.emit(TaskStatus.PAUSED.value)
            msg = self.task_logger.log("Task paused by user.")
            self.sig_log_message.emit(msg)

    @Slot()
    def resume_task(self) -> None:
        """Resume paused task execution."""
        if self._running and self._paused:
            self._paused = False
            if self.current_plan:
                self.current_plan.status = TaskStatus.RUNNING
            self.sig_status_changed.emit(TaskStatus.RUNNING.value)
            msg = self.task_logger.log("Task resumed.")
            self.sig_log_message.emit(msg)

    @Slot()
    def stop_task(self) -> None:
        """Emergency stop the running task and release all inputs."""
        self._stop_requested = True
        self._paused = False
        self._pending_approval = False

        if self.input_coordinator:
            self.input_coordinator.safety_release_all_inputs()

        if self.current_plan:
            self.current_plan.status = TaskStatus.STOPPED

        self.sig_status_changed.emit(TaskStatus.STOPPED.value)
        msg = self.task_logger.log("Task execution stopped immediately.")
        self.sig_log_message.emit(msg)

    @Slot(bool)
    def handle_user_approval(self, approved: bool) -> None:
        """Receive user authorization response for flagged risky step."""
        self._step_approved = approved
        self._pending_approval = False

    def run(self) -> None:
        """Main observe-plan-act-verify execution loop."""
        if not self.current_plan or not self.current_plan.steps:
            logger.warning("TaskExecutor started without a valid plan.")
            return

        if self._stop_requested:
            if self.current_plan:
                self.current_plan.status = TaskStatus.STOPPED
            self.sig_status_changed.emit(TaskStatus.STOPPED.value)
            if self.input_coordinator:
                self.input_coordinator.safety_release_all_inputs()
            return

        self._running = True
        self._paused = False
        self._stop_requested = False

        plan = self.current_plan
        plan.status = TaskStatus.RUNNING
        self.sig_status_changed.emit(TaskStatus.RUNNING.value)

        # 1. Acquire exclusive input ownership
        if self.input_coordinator:
            self.input_coordinator.acquire_agent_ownership()

        msg = self.task_logger.log(f"Started task: '{plan.instruction}' ({len(plan.steps)} steps)")
        self.sig_log_message.emit(msg)

        step_idx = 0
        while step_idx < len(plan.steps) and not self._stop_requested:
            # Handle pause
            while self._paused and not self._stop_requested:
                time.sleep(0.1)

            if self._stop_requested:
                break

            step = plan.steps[step_idx]

            # 2. Check safety approval requirement
            can_run, req_approval, reason = SafetyGuard.evaluate_step(step)
            if not can_run:
                step.status = StepStatus.FAILED
                step.error = reason
                self.sig_step_failed.emit(step.step_index, reason)
                msg = self.task_logger.log(f"Step {step.step_index + 1} blocked by policy: {reason}")
                self.sig_log_message.emit(msg)
                break

            if req_approval and not step.requires_confirmation:
                step.requires_confirmation = True

            if step.requires_confirmation:
                self._pending_approval = True
                self._step_approved = False
                plan.status = TaskStatus.WAITING_FOR_APPROVAL
                self.sig_status_changed.emit(TaskStatus.WAITING_FOR_APPROVAL.value)
                self.sig_confirmation_required.emit(step.step_index, step.description)

                msg = self.task_logger.log(f"Step {step.step_index + 1} waiting for user authorization...")
                self.sig_log_message.emit(msg)

                # Wait for user approval or stop
                while self._pending_approval and not self._stop_requested:
                    time.sleep(0.1)

                if self._stop_requested:
                    break

                if not self._step_approved:
                    step.status = StepStatus.SKIPPED
                    msg = self.task_logger.log(f"Step {step.step_index + 1} authorization declined by user.")
                    self.sig_log_message.emit(msg)
                    step_idx += 1
                    continue

                plan.status = TaskStatus.RUNNING
                self.sig_status_changed.emit(TaskStatus.RUNNING.value)

            # 3. Observe before acting
            plan.status = TaskStatus.OBSERVING
            self.sig_status_changed.emit(TaskStatus.OBSERVING.value)
            _, _, win_info = self.screen_observer.observe()

            # 4. Act visibly
            plan.status = TaskStatus.RUNNING
            self.sig_status_changed.emit(TaskStatus.RUNNING.value)
            step.status = StepStatus.IN_PROGRESS
            step.started_at = time.time()
            self.sig_step_started.emit(step.step_index, step.description)

            act_msg = self.task_logger.log(f"Executing step {step.step_index + 1}/{len(plan.steps)}: {step.description}")
            self.sig_log_message.emit(act_msg)

            success, err = self._execute_step(step, win_info)

            # 5. Verify outcome
            step.completed_at = time.time()
            if success:
                step.status = StepStatus.DONE
                self.sig_step_completed.emit(step.step_index)
            else:
                step.status = StepStatus.FAILED
                step.error = err
                self.sig_step_failed.emit(step.step_index, err or "Unknown error")
                plan.errors.append(f"Step {step.step_index + 1}: {err}")
                break

            step_idx += 1
            time.sleep(0.2)  # Short inter-step settling delay

        # 6. Finalize Task
        plan.completed_at = time.time()
        if self._stop_requested:
            plan.status = TaskStatus.STOPPED
        elif any(s.status == StepStatus.FAILED for s in plan.steps):
            plan.status = TaskStatus.FAILED
        else:
            plan.status = TaskStatus.COMPLETED

        self._running = False
        self.sig_status_changed.emit(plan.status.value)

        # 7. Release input ownership
        if self.input_coordinator:
            self.input_coordinator.release_agent_ownership(restore_headmouse=True)

        final_msg = self.task_logger.log(
            f"Task finished with status [{plan.status.value}]. "
            f"({plan.completed_steps_count}/{plan.total_steps} steps completed)"
        )
        self.sig_log_message.emit(final_msg)
        self.sig_task_completed.emit(plan.to_dict())

    def _execute_step(self, step: TaskStep, win_info: Optional[Any]) -> tuple[bool, Optional[str]]:
        """Dispatch single atomic step action to ActionController with agent-desktop UIA integration."""
        try:
            if step.action_type == ActionType.LAUNCH_APP:
                app_name = str(step.target or step.value or "")
                ok, msg = self.action_controller.launch_application(app_name)
                return ok, (None if ok else msg)

            elif step.action_type == ActionType.CLICK:
                target_str = str(step.target or "").strip()

                # Special handler: Save button in Save As dialog
                if target_str == "save_dialog_save_button":
                    adapter = self.action_controller.agent_desktop
                    win_list = adapter.list_windows(app_name="notepad.exe")
                    save_win = next((w for w in win_list if "Save As" in w.get("title", "")), None)
                    if not save_win:
                        return False, "Save As dialog window not found"

                    diag_id = save_win["id"]
                    res_save = adapter.find(window_id=diag_id, name="Save", timeout_ms=25000)
                    save_matches = [m for m in res_save if m.get("role") == "button" and m.get("name") == "Save"]
                    if not save_matches:
                        return False, "Save button not found in Save As dialog"

                    save_btn_ref = save_matches[0]["ref_id"]
                    adapter.hover(save_btn_ref, headed=True)
                    res_click = adapter.click(save_btn_ref, timeout_ms=25000)
                    if not res_click.get("ok", False):
                        return False, f"Failed clicking Save button: {res_click.get('error')}"

                    # Check for replace confirmation popup if file already existed
                    time.sleep(1.0)
                    win_list_after = adapter.list_windows(app_name="notepad.exe")
                    confirm_win = next(
                        (w for w in win_list_after if w.get("bounds", {}).get("height", 999) < 220), None
                    )
                    if confirm_win:
                        yes_matches = adapter.find(window_id=confirm_win["id"], role="button", name="Yes")
                        if yes_matches:
                            adapter.click(yes_matches[0]["ref_id"])

                    # Real disk verification
                    if hasattr(self, "_last_saved_filepath") and self._last_saved_filepath:
                        target_path = self._last_saved_filepath
                        for _ in range(20):
                            if os.path.exists(target_path):
                                break
                            time.sleep(0.5)

                        if not os.path.exists(target_path):
                            return False, f"Verification failed: file not found on disk at {target_path}"
                        logger.info(f"TaskExecutor verified real file created on disk: {target_path}")

                    return True, None

                # Ref ID click (@s...:e...)
                if target_str.startswith("@"):
                    ok = self.action_controller.click(ref_id=target_str, button="left")
                    return ok, (None if ok else "Click on ref failed")

                # Name target click
                if target_str and not isinstance(step.value, (list, tuple)):
                    adapter = self.action_controller.agent_desktop
                    if adapter and adapter.is_available():
                        matches = adapter.find(name=target_str)
                        if matches:
                            ok = self.action_controller.click(ref_id=matches[0]["ref_id"], button="left")
                            return ok, (None if ok else f"Click on '{target_str}' failed")

                # Coordinate-based click
                coords = step.value if isinstance(step.value, (list, tuple)) else None
                x = int(coords[0]) if coords and len(coords) >= 2 else None
                y = int(coords[1]) if coords and len(coords) >= 2 else None
                ok = self.action_controller.click(x, y, button="left")
                return ok, None

            elif step.action_type == ActionType.DOUBLE_CLICK:
                coords = step.value if isinstance(step.value, (list, tuple)) else None
                x = int(coords[0]) if coords and len(coords) >= 2 else None
                y = int(coords[1]) if coords and len(coords) >= 2 else None
                ok = self.action_controller.double_click(x, y)
                return ok, None

            elif step.action_type == ActionType.RIGHT_CLICK:
                coords = step.value if isinstance(step.value, (list, tuple)) else None
                x = int(coords[0]) if coords and len(coords) >= 2 else None
                y = int(coords[1]) if coords and len(coords) >= 2 else None
                ok = self.action_controller.click(x, y, button="right")
                return ok, None

            elif step.action_type == ActionType.TYPE_TEXT:
                text = str(step.value or "")
                target_str = str(step.target or "").strip()

                # Special handler: File name field in Save As dialog
                if target_str == "save_dialog_file_name":
                    adapter = self.action_controller.agent_desktop
                    desktop_dir = AgentDesktopAdapter.get_desktop_directory()
                    filename = os.path.basename(text) if text else "Jadoo_Test.txt"
                    target_file = os.path.join(desktop_dir, filename)
                    self._last_saved_filepath = target_file

                    # Locate Save As dialog window
                    win_list = adapter.list_windows(app_name="notepad.exe")
                    save_win = next((w for w in win_list if "Save As" in w.get("title", "")), None)
                    if not save_win and win_list:
                        hwnd = int(win_list[0]["id"].replace("w-", ""))
                        ctypes.windll.user32.PostMessageW(hwnd, 0x0111, 4, 0)
                        time.sleep(1.5)
                        win_list = adapter.list_windows(app_name="notepad.exe")
                        save_win = next((w for w in win_list if "Save As" in w.get("title", "")), None)

                    if not save_win:
                        return False, "Could not locate Save As dialog window"

                    diag_id = save_win["id"]
                    res_name = adapter.find(window_id=diag_id, name="File name", timeout_ms=25000)
                    name_matches = [m for m in res_name if m.get("role") == "textfield"]
                    if not name_matches:
                        return False, "File name textfield not found in Save As dialog"

                    res_set = adapter.set_value(name_matches[0]["ref_id"], target_file, timeout_ms=25000)
                    if not res_set.get("ok", False):
                        return False, f"Failed setting file path in dialog: {res_set.get('error')}"

                    return True, None

                # Special handler: Typing into Notepad document
                if target_str == "notepad":
                    adapter = self.action_controller.agent_desktop
                    if adapter and adapter.is_available():
                        doc_matches = adapter.find(app_name="notepad.exe", role="textfield")
                        if doc_matches:
                            res_set = adapter.set_value(doc_matches[0]["ref_id"], text)
                            if res_set.get("ok", False):
                                return True, None

                # Ref ID target
                if target_str.startswith("@"):
                    ok = self.action_controller.type_text(text, ref_id=target_str)
                    return ok, None

                ok = self.action_controller.type_text(text)
                return ok, None

            elif step.action_type == ActionType.PRESS_HOTKEY:
                keys = step.value if isinstance(step.value, (list, tuple)) else [str(step.value)]
                target_str = str(step.target or "").strip()

                # If saving in Notepad, attempt hotkey and ensure Save As dialog opens
                if keys in [["ctrl", "s"], ("ctrl", "s")] and target_str == "notepad":
                    self.action_controller.press_hotkey(*keys, app_name="notepad.exe")
                    time.sleep(1.0)
                    adapter = self.action_controller.agent_desktop
                    win_list = adapter.list_windows(app_name="notepad.exe")
                    if not any("Save As" in w.get("title", "") for w in win_list) and win_list:
                        hwnd = int(win_list[0]["id"].replace("w-", ""))
                        ctypes.windll.user32.PostMessageW(hwnd, 0x0111, 4, 0)
                        time.sleep(1.2)
                    return True, None

                ok = self.action_controller.press_hotkey(*keys)
                return ok, None

            elif step.action_type == ActionType.SCROLL:
                clicks = int(step.value or 0)
                ok = self.action_controller.scroll(clicks)
                return ok, None

            elif step.action_type == ActionType.WAIT:
                dur = float(step.value or 0.5)
                ok = self.action_controller.wait(dur)
                return ok, None

            elif step.action_type == ActionType.CAPTURE_SCREEN:
                _, _, _ = self.screen_observer.observe()
                return True, None

            else:
                return True, None

        except Exception as e:
            logger.error(f"Error during step execution ({step.description}): {e}")
            return False, str(e)
