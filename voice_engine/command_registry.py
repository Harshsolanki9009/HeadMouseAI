"""Predefined Voice Command Registry for Jadoo Accessibility System.

Defines canonical command identifiers, categories, comprehensive English and
Hinglish aliases, and support for loading custom user aliases from an external TOML file.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
import toml

from utils.logger import logger


class CommandCategory(str, Enum):
    """Functional categories for voice commands."""
    WAKE = "wake"
    DICTATION = "dictation"
    TEXT_EDITING = "text_editing"
    MOUSE = "mouse"
    TASK = "task"
    SAFETY = "safety"


class AccessibilityCommand(str, Enum):
    """Canonical voice commands supported by Jadoo."""
    # Wake
    WAKE_UP = "wake_up"

    # Dictation Mode Controls
    TYPING_ON = "typing_on"
    TYPING_OFF = "typing_off"

    # Text and Keyboard Actions
    BACKSPACE = "backspace"
    DELETE_WORD = "delete_word"
    CLEAR_FIELD = "clear_field"
    SELECT_ALL = "select_all"
    COPY = "copy"
    PASTE = "paste"
    ENTER = "enter"
    NEW_LINE = "new_line"
    UNDO = "undo"
    REDO = "redo"
    TAB = "tab"

    # Mouse & Navigation Actions
    MOUSE_ON = "mouse_on"
    MOUSE_OFF = "mouse_off"
    SCROLL_UP = "scroll_up"
    SCROLL_DOWN = "scroll_down"
    RECENTER = "recenter"
    CALIBRATE_CURSOR = "calibrate_cursor"
    PAUSE_CURSOR = "pause_cursor"
    RESUME_CURSOR = "resume_cursor"

    # Autonomous Task Agent Actions
    START_TASK = "start_task"
    PAUSE_TASK = "pause_task"
    RESUME_TASK = "resume_task"
    STOP_TASK = "stop_task"

    # Safety Actions
    STOP_ALL = "stop_all"
    EMERGENCY_STOP = "emergency_stop"


# Map each canonical command to its category
COMMAND_CATEGORY_MAP: Dict[AccessibilityCommand, CommandCategory] = {
    AccessibilityCommand.WAKE_UP: CommandCategory.WAKE,
    AccessibilityCommand.TYPING_ON: CommandCategory.DICTATION,
    AccessibilityCommand.TYPING_OFF: CommandCategory.DICTATION,
    AccessibilityCommand.BACKSPACE: CommandCategory.TEXT_EDITING,
    AccessibilityCommand.DELETE_WORD: CommandCategory.TEXT_EDITING,
    AccessibilityCommand.CLEAR_FIELD: CommandCategory.TEXT_EDITING,
    AccessibilityCommand.SELECT_ALL: CommandCategory.TEXT_EDITING,
    AccessibilityCommand.COPY: CommandCategory.TEXT_EDITING,
    AccessibilityCommand.PASTE: CommandCategory.TEXT_EDITING,
    AccessibilityCommand.ENTER: CommandCategory.TEXT_EDITING,
    AccessibilityCommand.NEW_LINE: CommandCategory.TEXT_EDITING,
    AccessibilityCommand.UNDO: CommandCategory.TEXT_EDITING,
    AccessibilityCommand.REDO: CommandCategory.TEXT_EDITING,
    AccessibilityCommand.TAB: CommandCategory.TEXT_EDITING,
    AccessibilityCommand.MOUSE_ON: CommandCategory.MOUSE,
    AccessibilityCommand.MOUSE_OFF: CommandCategory.MOUSE,
    AccessibilityCommand.SCROLL_UP: CommandCategory.MOUSE,
    AccessibilityCommand.SCROLL_DOWN: CommandCategory.MOUSE,
    AccessibilityCommand.RECENTER: CommandCategory.MOUSE,
    AccessibilityCommand.CALIBRATE_CURSOR: CommandCategory.MOUSE,
    AccessibilityCommand.PAUSE_CURSOR: CommandCategory.MOUSE,
    AccessibilityCommand.RESUME_CURSOR: CommandCategory.MOUSE,
    AccessibilityCommand.START_TASK: CommandCategory.TASK,
    AccessibilityCommand.PAUSE_TASK: CommandCategory.TASK,
    AccessibilityCommand.RESUME_TASK: CommandCategory.TASK,
    AccessibilityCommand.STOP_TASK: CommandCategory.TASK,
    AccessibilityCommand.STOP_ALL: CommandCategory.SAFETY,
    AccessibilityCommand.EMERGENCY_STOP: CommandCategory.SAFETY,
}

# Default English and Hinglish recognition aliases
DEFAULT_COMMAND_ALIASES: Dict[AccessibilityCommand, List[str]] = {
    AccessibilityCommand.WAKE_UP: [
        "hey jadoo",
        "hello jadoo",
        "hi jadoo",
        "jadoo wake up",
        "wake up jadoo",
        "ok jadoo",
        "सुनो जादू",
        "हे जादू",
        "नमस्ते जादू",
        "जादू जागो",
    ],
    AccessibilityCommand.TYPING_ON: [
        "typing on",
        "start typing",
        "start dictation",
        "dictation on",
        "begin typing",
        "turn on typing",
        "टाइपिंग ऑन",
        "टाइपिंग शुरू",
        "लिखना शुरू",
        "डिक्टेशन शुरू",
        "बोलना शुरू",
    ],
    AccessibilityCommand.TYPING_OFF: [
        "typing off",
        "stop typing",
        "stop dictation",
        "dictation off",
        "end typing",
        "turn off typing",
        "finish typing",
        "टाइपिंग ऑफ",
        "टाइपिंग बंद",
        "लिखना बंद",
        "डिक्टेशन बंद",
        "बोलना बंद",
    ],
    AccessibilityCommand.BACKSPACE: [
        "backspace",
        "press backspace",
        "back space",
        "erase character",
        "बैकस्पेस",
        "एक अक्षर हटाओ",
        "काटो",
    ],
    AccessibilityCommand.DELETE_WORD: [
        "delete word",
        "delete last word",
        "erase word",
        "remove word",
        "डिलीट वर्ड",
        "शब्द हटाओ",
        "आखिरी शब्द हटाओ",
    ],
    AccessibilityCommand.CLEAR_FIELD: [
        "clear all",
        "clear field",
        "clear current field",
        "clear text",
        "erase all",
        "empty field",
        "पूरा मिटाओ",
        "सब हटाओ",
        "टेक्स्ट साफ करो",
        "खाली करो",
    ],
    AccessibilityCommand.SELECT_ALL: [
        "select all",
        "select everything",
        "highlight all",
        "सेलेक्ट ऑल",
        "सब चुनो",
        "पूरा चुनो",
    ],
    AccessibilityCommand.COPY: [
        "copy that",
        "copy this",
        "copy",
        "कॉपी",
        "कॉपी करो",
        "नकल करो",
    ],
    AccessibilityCommand.PASTE: [
        "paste",
        "paste that",
        "paste here",
        "पेस्ट",
        "पेस्ट करो",
        "चिपकाओ",
    ],
    AccessibilityCommand.ENTER: [
        "press enter",
        "hit enter",
        "enter",
        "send",
        "एंटर",
        "एंटर दबाओ",
    ],
    AccessibilityCommand.NEW_LINE: [
        "new line",
        "next line",
        "line break",
        "न्यू लाइन",
        "नई लाइन",
        "अगली लाइन",
    ],
    AccessibilityCommand.UNDO: [
        "undo",
        "undo that",
        "revert",
        "अंडू",
        "वापस लो",
        "पहले जैसा",
    ],
    AccessibilityCommand.REDO: [
        "redo",
        "redo that",
        "रीडू",
        "फिर से करो",
    ],
    AccessibilityCommand.TAB: [
        "tab",
        "press tab",
        "next field",
        "टैब",
        "टैब दबाओ",
        "अगला फील्ड",
    ],
    AccessibilityCommand.MOUSE_ON: [
        "mouse on",
        "enable mouse",
        "turn on mouse",
        "turn on head mouse",
        "start mouse",
        "start head mouse",
        "head mouse on",
        "माउस ऑन",
        "माउस चालू",
        "माउस शुरू",
        "हेड माउस चालू",
        "हेड माउस ऑन",
    ],
    AccessibilityCommand.MOUSE_OFF: [
        "mouse off",
        "disable mouse",
        "turn off mouse",
        "turn off head mouse",
        "stop mouse",
        "stop head mouse",
        "head mouse off",
        "माउस ऑफ",
        "माउस बंद",
        "माउस रोको",
        "हेड माउस बंद",
        "हेड माउस ऑफ",
    ],
    AccessibilityCommand.SCROLL_UP: [
        "scroll up",
        "page up",
        "move up",
        "स्क्रॉल अप",
        "ऊपर स्क्रॉल",
        "ऊपर चलो",
    ],
    AccessibilityCommand.SCROLL_DOWN: [
        "scroll down",
        "page down",
        "move down",
        "स्क्रॉल डाउन",
        "नीचे स्क्रॉल",
        "नीचे चलो",
    ],
    AccessibilityCommand.RECENTER: [
        "recenter",
        "re center",
        "center cursor",
        "recenter cursor",
        "recenter head",
        "recenter mouse",
        "कर्सर रीसेंटर",
        "माउस रीसेंटर",
        "रीसेंटर",
        "सेंटर",
        "बीच में",
    ],
    AccessibilityCommand.CALIBRATE_CURSOR: [
        "calibrate cursor",
        "calibrate head",
        "start calibration",
        "calibrate mouse",
        "calibrate my mouse",
        "calibrate the mouse",
        "कर्सर कैलिब्रेट",
        "कैलिब्रेशन शुरू",
        "कैलिब्रेट",
        "माउस कैलिब्रेट करो",
    ],
    AccessibilityCommand.PAUSE_CURSOR: [
        "pause cursor",
        "pause mouse",
        "pause tracking",
        "कर्सर रोको",
        "माउस पॉज़",
        "पॉज़ कर्सर",
    ],
    AccessibilityCommand.RESUME_CURSOR: [
        "resume cursor",
        "resume mouse",
        "unpause cursor",
        "resume tracking",
        "कर्सर चलाओ",
        "माउस शुरू करो",
        "रिज्यूम कर्सर",
    ],
    AccessibilityCommand.START_TASK: [
        "start task",
        "run task",
        "execute task",
        "start agent",
        "run agent",
        "start autonomous mode",
        "autonomous mode on",
        "autonomous mode",
        "टास्क शुरू करो",
        "काम शुरू करो",
        "एजेंट शुरू करो",
        "ऑटोनॉमस मोड चालू",
        "ऑटोनॉमस मोड",
    ],
    AccessibilityCommand.PAUSE_TASK: [
        "pause task",
        "hold task",
        "pause agent",
        "pause the agent",
        "टास्क रोको",
        "काम रोको",
        "एजेंट रोको",
    ],
    AccessibilityCommand.RESUME_TASK: [
        "resume task",
        "continue task",
        "resume agent",
        "resume the agent",
        "टास्क जारी रखो",
        "काम जारी रखो",
        "एजेंट चालू रखो",
    ],
    AccessibilityCommand.STOP_TASK: [
        "stop task",
        "abort task",
        "cancel task",
        "kill task",
        "stop agent",
        "stop the agent",
        "टास्क बंद करो",
        "काम बंद करो",
        "टास्क रद्द करो",
    ],
    AccessibilityCommand.STOP_ALL: [
        "stop all",
        "stop jadoo",
        "stop everything",
        "halt all",
        "pause all",
        "सब रोको",
        "जादू रुको",
        "सब बंद",
        "सब रोक दो",
        "सब बंद करो",
    ],
    AccessibilityCommand.EMERGENCY_STOP: [
        "emergency stop",
        "emergency halt",
        "emergency abort",
        "kill switch",
        "इमरजेंसी स्टॉप",
        "इमरजेंसी",
        "आपातकालीन रोक",
    ],
}


class CommandRegistry:
    """Manages command aliases, categories, and custom configuration file overrides."""

    def __init__(self, custom_config_path: Optional[Path | str] = None) -> None:
        self._aliases: Dict[AccessibilityCommand, List[str]] = {
            cmd: list(aliases) for cmd, aliases in DEFAULT_COMMAND_ALIASES.items()
        }
        self.config_path: Optional[Path] = Path(custom_config_path) if custom_config_path else None
        self._load_custom_config()

    def _load_custom_config(self) -> None:
        """Merge custom aliases from TOML file if present."""
        if not self.config_path:
            # Check default path config/voice_commands.toml
            default_path = Path(__file__).resolve().parent.parent / "config" / "voice_commands.toml"
            if default_path.is_file():
                self.config_path = default_path

        if self.config_path and self.config_path.is_file():
            try:
                data = toml.load(str(self.config_path))
                custom_commands = data.get("commands", {})
                for cmd_str, aliases in custom_commands.items():
                    try:
                        cmd = AccessibilityCommand(cmd_str.lower())
                        if isinstance(aliases, list):
                            for alias in aliases:
                                alias_clean = str(alias).strip()
                                if alias_clean and alias_clean not in self._aliases[cmd]:
                                    self._aliases[cmd].append(alias_clean)
                    except ValueError:
                        logger.warning(f"Unknown command key '{cmd_str}' in custom command config.")
                logger.info(f"Loaded custom voice commands from {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load custom voice commands config: {e}")

    def get_aliases(self, command: AccessibilityCommand) -> List[str]:
        """Return list of alias phrases for a specific command."""
        return self._aliases.get(command, [])

    def get_all_aliases(self) -> Dict[AccessibilityCommand, List[str]]:
        """Return full map of commands to alias lists."""
        return self._aliases

    def get_category(self, command: AccessibilityCommand) -> CommandCategory:
        """Return functional category for command."""
        return COMMAND_CATEGORY_MAP.get(command, CommandCategory.TEXT_EDITING)
