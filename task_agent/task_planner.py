"""Task Planner for Jadoo Autonomous Desktop Agent.

Decomposes natural language desktop instructions into sequential atomic TaskSteps
using Gemini 2.5 Flash with fast deterministic fallback templates.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from ai_provider.gemini_client import GeminiClient
from task_agent.safety_guard import SafetyGuard
from task_agent.task_state import ActionType, StepStatus, TaskPlan, TaskStep
from utils.logger import logger

PLANNER_SYSTEM_PROMPT = """You are Jadoo Autonomous Desktop Task Planner.
Your role is to decompose a user desktop automation request on Windows into sequential atomic steps.
Allowed action types:
- launch_app: target is application name (e.g., "notepad", "chrome", "calc", "explorer")
- click: target description, value optional coordinates [x, y]
- type_text: value is exact text to type
- press_hotkey: value is list of keys (e.g., ["ctrl", "s"], ["enter"])
- scroll: value is integer clicks (e.g., -300 or 300)
- wait: value is seconds (e.g., 2.0)
- user_confirmation: description of risky action requiring explicit approval

Output strictly valid JSON with no markdown formatting:
{
  "summary": "Short 1-sentence goal summary",
  "steps": [
    {"action": "launch_app", "target": "notepad", "description": "Open Notepad"},
    {"action": "type_text", "value": "Hello world", "description": "Type text into Notepad"}
  ]
}
"""


class TaskPlanner:
    """Creates structured TaskPlans from natural language instructions."""

    def __init__(self, gemini_client: Optional[GeminiClient] = None) -> None:
        self.gemini = gemini_client or GeminiClient()

    def plan_instruction(self, instruction: str) -> TaskPlan:
        """Decompose natural language instruction into an executable TaskPlan."""
        clean_text = instruction.strip()
        logger.info(f"TaskPlanner generating plan for: '{clean_text}'")

        # 1. First check deterministic fast templates
        fast_plan = self._try_deterministic_template(clean_text)
        if fast_plan is not None:
            logger.info(f"TaskPlanner applied fast deterministic template ({len(fast_plan.steps)} steps).")
            return fast_plan

        # 2. Use Gemini AI planning if configured
        if self.gemini.is_configured:
            try:
                ai_plan = self._plan_with_gemini(clean_text)
                if ai_plan and ai_plan.steps:
                    logger.info(f"TaskPlanner generated AI plan via Gemini ({len(ai_plan.steps)} steps).")
                    return ai_plan
            except Exception as e:
                logger.warning(f"TaskPlanner Gemini planning error: {e}. Falling back to default plan.")

        # 3. Fallback generic single-step action
        return self._create_generic_fallback_plan(clean_text)

    def _try_deterministic_template(self, text: str) -> Optional[TaskPlan]:
        """Match common user patterns (e.g. open notepad, search in browser)."""
        clean = re.sub(r"^(?:hey\s+)?jadoo[,\s]+", "", text, flags=re.IGNORECASE).strip()
        lower = clean.lower()

        # Pattern: Open Chrome / Launch Chrome
        if re.search(r"^\s*(?:open|launch)\s+(?:google\s+)?chrome\s*$", lower):
            plan = TaskPlan(instruction=text, summary="Launch Google Chrome browser")
            plan.steps = [
                TaskStep(0, ActionType.LAUNCH_APP, "Launch Chrome Browser", target="chrome"),
                TaskStep(1, ActionType.WAIT, "Wait for Chrome window", value=1.5),
            ]
            self._apply_safety_annotations(plan)
            return plan

        # Pattern: Open YouTube and search for <query>
        if "youtube" in lower:
            m_yt = re.search(
                r"(?:open\s+youtube\s+(?:and\s+)?search\s+(?:for\s+)?|search\s+(?:for\s+)?)(.+?)(?:\s+on\s+youtube|$)",
                clean,
                re.IGNORECASE,
            )
            yt_query = m_yt.group(1).strip() if (m_yt and m_yt.group(1).strip()) else "tutorial"
            encoded = yt_query.replace(" ", "+")
            plan = TaskPlan(instruction=text, summary=f"Search YouTube for '{yt_query}'")
            plan.steps = [
                TaskStep(
                    0,
                    ActionType.LAUNCH_APP,
                    "Open YouTube Search in Browser",
                    target=f"https://www.youtube.com/results?search_query={encoded}",
                ),
                TaskStep(1, ActionType.WAIT, "Wait for browser window to load", value=2.0),
                TaskStep(2, ActionType.CAPTURE_SCREEN, "Observe search results"),
            ]
            self._apply_safety_annotations(plan)
            return plan

        # Pattern: Open Notepad and write a leave application
        if re.search(r"open\s+notepad\s+(?:and\s+)?write\s+(?:a\s+)?leave\s+application", lower):
            leave_text = (
                "Subject: Leave Application\n\n"
                "Dear Sir/Madam,\n\n"
                "I am writing to formally request leave for two days due to urgent personal work. "
                "I will ensure all pending tasks are updated and resume work promptly.\n\n"
                "Thank you for your understanding.\n\n"
                "Sincerely,\n"
                "Your Name"
            )
            plan = TaskPlan(instruction=text, summary="Open Notepad and write professional leave application")
            plan.steps = [
                TaskStep(0, ActionType.LAUNCH_APP, "Launch Notepad", target="notepad"),
                TaskStep(1, ActionType.WAIT, "Wait for Notepad window", value=1.0),
                TaskStep(2, ActionType.TYPE_TEXT, "Type leave application into Notepad", target="notepad", value=leave_text),
                TaskStep(3, ActionType.WAIT, "Wait for typing completion", value=0.5),
            ]
            self._apply_safety_annotations(plan)
            return plan

        # Pattern: Create a folder named <name>
        m_folder = re.search(r"create\s+(?:a\s+)?folder\s+(?:named|called)?\s*([a-zA-Z0-9_\-\s]+)", clean, re.IGNORECASE)
        if m_folder:
            folder_name = m_folder.group(1).strip()
            import os
            from task_agent.agent_desktop_adapter import AgentDesktopAdapter
            desktop_dir = AgentDesktopAdapter.get_desktop_directory()
            target_folder = os.path.join(desktop_dir, folder_name)
            os.makedirs(target_folder, exist_ok=True)
            plan = TaskPlan(instruction=text, summary=f"Create folder '{folder_name}' on Desktop")
            plan.steps = [
                TaskStep(0, ActionType.LAUNCH_APP, f"Open folder '{folder_name}' in Explorer", target=target_folder),
                TaskStep(1, ActionType.WAIT, "Wait for Explorer window", value=1.0),
                TaskStep(2, ActionType.CAPTURE_SCREEN, "Verify created folder in Explorer"),
            ]
            self._apply_safety_annotations(plan)
            return plan

        # Pattern: Open my project folder and find Python file
        if re.search(r"open\s+(?:my\s+)?project\s+folder(?:\s+and\s+find\s+(?:the\s+)?python\s+file)?", lower):
            import os
            project_dir = os.path.abspath(".")
            plan = TaskPlan(instruction=text, summary=f"Open project folder in Explorer")
            plan.steps = [
                TaskStep(0, ActionType.LAUNCH_APP, "Open Project Directory in Explorer", target=project_dir),
                TaskStep(1, ActionType.WAIT, "Wait for Explorer window", value=1.5),
                TaskStep(2, ActionType.CAPTURE_SCREEN, "Observe project directory contents"),
            ]
            self._apply_safety_annotations(plan)
            return plan

        # Pattern: Open Notepad, type <text> and save (it) on/to desktop as <filename>
        m_notepad_save = re.search(
            r"open\s+notepad(?:\s*,\s*|\s+and\s+)?(?:type|write)\s+(.+?)(?:\s+and\s+)?save\s+(?:it\s+)?(?:on|to)\s+(?:the\s+)?desktop\s+as\s+([^\s\.]+(?:\.[a-zA-Z0-9]+)?)",
            text,
            re.IGNORECASE,
        )
        if m_notepad_save:
            content_to_write = m_notepad_save.group(1).strip()
            filename = m_notepad_save.group(2).strip()
            if not filename.endswith(".txt"):
                filename += ".txt"

            plan = TaskPlan(
                instruction=text,
                summary=f"Open Notepad, type '{content_to_write[:25]}' and save on Desktop as '{filename}'",
            )
            plan.steps = [
                TaskStep(0, ActionType.LAUNCH_APP, "Launch Notepad", target="notepad"),
                TaskStep(1, ActionType.WAIT, "Wait for Notepad window", value=1.0),
                TaskStep(2, ActionType.TYPE_TEXT, "Type content into Notepad", target="notepad", value=content_to_write),
                TaskStep(3, ActionType.PRESS_HOTKEY, "Open Save As dialog", target="notepad", value=["ctrl", "s"]),
                TaskStep(4, ActionType.WAIT, "Wait for Save As dialog", value=1.0),
                TaskStep(5, ActionType.TYPE_TEXT, "Set file destination path", target="save_dialog_file_name", value=filename),
                TaskStep(6, ActionType.CLICK, "Click Save button", target="save_dialog_save_button"),
                TaskStep(7, ActionType.WAIT, "Wait for file save to complete", value=1.5),
            ]
            self._apply_safety_annotations(plan)
            return plan

        # Pattern: Open Notepad and write/type <text>
        m_notepad_write = re.search(r"open\s+notepad(?:\s+and)?\s+(?:write|type)\s+(.+)", text, re.IGNORECASE)
        if m_notepad_write:
            content_to_write = m_notepad_write.group(1).strip()
            plan = TaskPlan(instruction=text, summary=f"Open Notepad and type '{content_to_write[:30]}'")
            plan.steps = [
                TaskStep(0, ActionType.LAUNCH_APP, "Launch Notepad", target="notepad"),
                TaskStep(1, ActionType.WAIT, "Wait for Notepad window", value=1.0),
                TaskStep(2, ActionType.TYPE_TEXT, "Type content into Notepad", value=content_to_write),
            ]
            self._apply_safety_annotations(plan)
            return plan

        # Pattern: Open Notepad
        if re.search(r"^\s*open\s+notepad\s*$", lower):
            plan = TaskPlan(instruction=text, summary="Launch Notepad application")
            plan.steps = [TaskStep(0, ActionType.LAUNCH_APP, "Launch Notepad", target="notepad")]
            self._apply_safety_annotations(plan)
            return plan

        # Pattern: Open Calculator and calculate <expression>
        m_calc_expr = re.search(
            r"open\s+(?:calculator|calc)(?:\s+and)?\s+calculate\s+(.+)",
            text,
            re.IGNORECASE,
        )
        if m_calc_expr:
            expr_raw = m_calc_expr.group(1).strip()
            calc_keys = (
                expr_raw.replace("multiplied by", "*")
                .replace("times", "*")
                .replace("x", "*")
                .replace("plus", "+")
                .replace("minus", "-")
                .replace("divided by", "/")
                .replace(" ", "")
            )
            if not calc_keys.endswith("="):
                calc_keys += "="

            plan = TaskPlan(
                instruction=text,
                summary=f"Open Calculator and calculate '{expr_raw}'",
            )
            plan.steps = [
                TaskStep(0, ActionType.LAUNCH_APP, "Launch Calculator", target="calc"),
                TaskStep(1, ActionType.WAIT, "Wait for Calculator window", value=1.5),
                TaskStep(2, ActionType.TYPE_TEXT, f"Enter calculation: {calc_keys}", target="calc", value=calc_keys),
                TaskStep(3, ActionType.WAIT, "Wait for result calculation", value=1.0),
                TaskStep(4, ActionType.CAPTURE_SCREEN, "Observe calculation result"),
            ]
            self._apply_safety_annotations(plan)
            return plan

        # Pattern: Open Calculator
        if re.search(r"^\s*open\s+(?:calculator|calc)\s*$", lower):
            plan = TaskPlan(instruction=text, summary="Launch Calculator application")
            plan.steps = [TaskStep(0, ActionType.LAUNCH_APP, "Launch Calculator", target="calc")]
            self._apply_safety_annotations(plan)
            return plan

        # Pattern: Open Chrome / Edge and search for <query>
        m_search = re.search(r"(?:open\s+(?:chrome|browser|google)\s+(?:and\s+)?search\s+(?:for\s+)?|search\s+(?:for\s+)?)(.+?)(?:\s+on\s+google|\s+in\s+chrome|$)", text, re.IGNORECASE)
        if m_search:
            query = m_search.group(1).strip().rstrip(".")
            plan = TaskPlan(instruction=text, summary=f"Search Google for '{query}'")
            plan.steps = [
                TaskStep(0, ActionType.LAUNCH_APP, "Launch Chrome Browser", target="chrome"),
                TaskStep(1, ActionType.WAIT, "Wait for browser window", value=1.5),
                TaskStep(2, ActionType.PRESS_HOTKEY, "Focus address bar", value=["ctrl", "l"]),
                TaskStep(3, ActionType.TYPE_TEXT, f"Type search query: {query}", value=f"https://www.google.com/search?q={query.replace(' ', '+')}"),
                TaskStep(4, ActionType.PRESS_HOTKEY, "Execute search", value=["enter"]),
            ]
            self._apply_safety_annotations(plan)
            return plan

        return None

    def _plan_with_gemini(self, instruction: str) -> Optional[TaskPlan]:
        """Query Gemini 2.5 Flash for step-by-step automation decomposition."""
        resp = self.gemini.generate_content(
            prompt=f"User Task Instruction: '{instruction}'",
            system_instruction=PLANNER_SYSTEM_PROMPT,
            temperature=0.2,
        )
        raw_text = resp.get("text", "")
        if not raw_text:
            return None

        # Clean JSON block
        clean_json = raw_text.strip()
        if clean_json.startswith("```"):
            clean_json = re.sub(r"^```(?:json)?\s*", "", clean_json)
            clean_json = re.sub(r"\s*```$", "", clean_json)

        data = json.loads(clean_json)
        summary = data.get("summary", instruction)
        raw_steps = data.get("steps", [])

        plan = TaskPlan(instruction=instruction, summary=summary)
        for idx, s in enumerate(raw_steps):
            act_str = str(s.get("action", "wait")).lower()
            try:
                act_type = ActionType(act_str)
            except ValueError:
                act_type = ActionType.WAIT

            desc = s.get("description", f"Step {idx + 1}")
            target = str(s.get("target", ""))
            val = s.get("value")

            step = TaskStep(idx, act_type, desc, target=target, value=val)
            plan.steps.append(step)

        self._apply_safety_annotations(plan)
        return plan

    def _create_generic_fallback_plan(self, instruction: str) -> TaskPlan:
        """Create single safe fallback step if no template matches and Gemini unavailable."""
        plan = TaskPlan(instruction=instruction, summary="Execute instruction")
        plan.steps = [
            TaskStep(0, ActionType.WAIT, f"Review instruction: {instruction[:40]}", value=0.5)
        ]
        self._apply_safety_annotations(plan)
        return plan

    def _apply_safety_annotations(self, plan: TaskPlan) -> None:
        """Pass each step through SafetyGuard to annotate risk and confirmation requirements."""
        for step in plan.steps:
            can_run, req_approval, reason = SafetyGuard.evaluate_step(step)
            if not can_run:
                step.is_risky = True
                step.requires_confirmation = True
                step.error = reason
            elif req_approval:
                step.is_risky = True
                step.requires_confirmation = True
