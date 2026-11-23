"""Task State, Status Enums, and Data Models for Jadoo Task Agent.

Defines the lifecycle states, step representations, and plan structures
for multi-step desktop automation.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    """Lifecycle states of an autonomous desktop task."""
    PLANNING = "PLANNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    RUNNING = "RUNNING"
    OBSERVING = "OBSERVING"
    RETRYING = "RETRYING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    STOPPED = "STOPPED"


class ActionType(str, Enum):
    """Atomic desktop action types."""
    LAUNCH_APP = "launch_app"
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    TYPE_TEXT = "type_text"
    PRESS_HOTKEY = "press_hotkey"
    PRESS_KEY = "press_key"
    SCROLL = "scroll"
    WAIT = "wait"
    CAPTURE_SCREEN = "capture_screen"
    USER_CONFIRMATION = "user_confirmation"


class StepStatus(str, Enum):
    """Execution status of an individual task step."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class TaskStep:
    """Represents a single atomic action within a task plan."""
    step_index: int
    action_type: ActionType
    description: str
    target: str = ""                         # Application name, element title, or coordinates
    value: Any = None                        # Text to type, hotkey tuple, scroll amount, or target (x, y)
    is_risky: bool = False                   # Flagged if destructive or financial
    requires_confirmation: bool = False      # Requires explicit user popup approval
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to JSON-serializable dictionary."""
        d = asdict(self)
        d["action_type"] = self.action_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TaskStep:
        """Instantiate step from dictionary."""
        act_type = ActionType(data.get("action_type", ActionType.WAIT.value))
        st = StepStatus(data.get("status", StepStatus.PENDING.value))
        return cls(
            step_index=int(data.get("step_index", 0)),
            action_type=act_type,
            description=str(data.get("description", "")),
            target=str(data.get("target", "")),
            value=data.get("value"),
            is_risky=bool(data.get("is_risky", False)),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            status=st,
            error=data.get("error"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
        )


@dataclass
class TaskPlan:
    """Represents a full multi-step execution plan for an instruction."""
    instruction: str
    steps: List[TaskStep] = field(default_factory=list)
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: TaskStatus = TaskStatus.PLANNING
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    summary: str = ""
    files_created: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.DONE)

    def to_dict(self) -> Dict[str, Any]:
        """Convert plan to dictionary."""
        return {
            "task_id": self.task_id,
            "instruction": self.instruction,
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "summary": self.summary,
            "files_created": self.files_created,
            "errors": self.errors,
            "steps": [s.to_dict() for s in self.steps],
        }
