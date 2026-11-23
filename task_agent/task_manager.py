"""Top-Level Task Manager for Jadoo Autonomous Desktop Agent.

Coordinates planning, execution, visible overlay feedback, input ownership,
and Qt UI signals.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal, Slot

from ai_provider.gemini_client import GeminiClient
from task_agent.action_controller import ActionController
from task_agent.action_overlay import ActionOverlay
from task_agent.input_coordinator import InputOwnershipCoordinator
from task_agent.screen_observer import ScreenObserver
from task_agent.task_executor import TaskExecutor
from task_agent.task_logger import TaskLogger
from task_agent.task_planner import TaskPlanner
from task_agent.task_state import TaskPlan, TaskStatus
from utils.logger import logger


class TaskManager(QObject):
    """Facade orchestrating all Task Agent components."""

    # Outgoing Signals to Desktop GUI & Floating Panel
    sig_plan_ready = Signal(dict)                # Plan JSON dictionary
    sig_status_changed = Signal(str)             # TaskStatus value
    sig_step_started = Signal(int, str)          # (step_index, description)
    sig_step_completed = Signal(int)             # step_index
    sig_step_failed = Signal(int, str)           # (step_index, error)
    sig_confirmation_required = Signal(int, str) # (step_index, description)
    sig_task_completed = Signal(dict)            # Final report dict
    sig_log_message = Signal(str)                # Activity log line

    def __init__(
        self,
        gemini_client: Optional[GeminiClient] = None,
        vision_worker: Optional[Any] = None,
        keyboard_controller: Optional[Any] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)

        # Core Subsystems
        self.task_logger = TaskLogger()
        self.overlay = ActionOverlay()
        self.action_controller = ActionController(overlay=self.overlay)
        self.screen_observer = ScreenObserver()
        self.input_coordinator = InputOwnershipCoordinator(
            vision_worker=vision_worker,
            keyboard_controller=keyboard_controller,
        )
        self.planner = TaskPlanner(gemini_client=gemini_client)
        self.executor = TaskExecutor(
            action_controller=self.action_controller,
            screen_observer=self.screen_observer,
            input_coordinator=self.input_coordinator,
            task_logger=self.task_logger,
            parent=self,
        )

        # Connect executor signals to manager signals
        self.executor.sig_status_changed.connect(self.sig_status_changed)
        self.executor.sig_step_started.connect(self.sig_step_started)
        self.executor.sig_step_completed.connect(self.sig_step_completed)
        self.executor.sig_step_failed.connect(self.sig_step_failed)
        self.executor.sig_confirmation_required.connect(self.sig_confirmation_required)
        self.executor.sig_task_completed.connect(self._on_task_finished)
        self.executor.sig_log_message.connect(self.sig_log_message)

        self.current_plan: Optional[TaskPlan] = None

    @property
    def is_running(self) -> bool:
        """True while task executor thread is running."""
        return self.executor.isRunning()

    @Slot(str)
    def submit_instruction(self, instruction: str) -> TaskPlan:
        """Process natural language request, create plan, and prepare for execution."""
        clean = instruction.strip()
        if not clean:
            return TaskPlan(instruction="")

        msg = self.task_logger.log(f"Received instruction: '{clean}'")
        self.sig_log_message.emit(msg)

        plan = self.planner.plan_instruction(clean)
        self.current_plan = plan
        self.executor.set_plan(plan)

        self.sig_plan_ready.emit(plan.to_dict())
        self.sig_status_changed.emit(plan.status.value)
        return plan

    @Slot()
    def start_task(self) -> None:
        """Start executing the currently planned task."""
        if not self.current_plan or not self.current_plan.steps:
            logger.warning("No active task plan to start.")
            return
        if not self.executor.isRunning():
            self.executor.start()

    @Slot()
    def pause_task(self) -> None:
        """Pause active task execution."""
        self.executor.pause_task()
        if self.overlay:
            self.overlay.show_action("TASK PAUSED", duration_ms=0)

    @Slot()
    def resume_task(self) -> None:
        """Resume paused task execution."""
        self.executor.resume_task()
        if self.overlay:
            self.overlay.clear_action()

    @Slot()
    def stop_task(self) -> None:
        """Emergency stop active task."""
        self.executor.stop_task()
        if self.overlay:
            self.overlay.show_action("TASK STOPPED", duration_ms=2500)

    @Slot(bool)
    def authorize_step(self, approved: bool) -> None:
        """User confirmation for flagged risky step."""
        self.executor.handle_user_approval(approved)

    def _on_task_finished(self, report: dict) -> None:
        """Cleanup after task finishes."""
        if self.overlay:
            st = report.get("status", "COMPLETED")
            self.overlay.show_action(f"TASK {st}", duration_ms=2500)
        self.sig_task_completed.emit(report)

    def cleanup(self) -> None:
        """Safe shutdown."""
        self.stop_task()
        if self.overlay:
            self.overlay.close()
        if self.executor.isRunning():
            self.executor.wait(1500)
