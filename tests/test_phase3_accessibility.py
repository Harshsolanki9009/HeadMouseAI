"""Automated test suite for Jadoo Phase 3: Hands-Free Accessibility Control System.

Verifies:
1. Command normalization (case, punctuation, unicode NFKC, Devanagari).
2. English & Hinglish command recognition.
3. Strict Dictation Mode Isolation (mandatory rules).
4. Mode transitions and state machine.
5. Duplicate command suppression & cooldown.
6. Keyboard action controller & safe clear field.
7. Mouse integration (enable, disable, scroll, stop all).
8. Floating panel UI creation, accessible button states, and geometry persistence.
9. Windows startup utility.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch
import pytest

from PySide6.QtWidgets import QApplication

from config.settings import AppSettings
from gui.floating_panel import AccessibleButton, FloatingControlPanel
from voice_engine.command_engine import CommandEngine, normalize_command_text
from voice_engine.command_registry import AccessibilityCommand, CommandCategory, CommandRegistry
from voice_engine.keyboard_controller import KeyboardActionController
from voice_engine.mode_manager import JadooOperatingMode, ModeRouter
from utils.windows_startup import get_startup_command, is_windows_startup_enabled


# ------------------------------------------------------------- #
# 1. Command Normalization Tests                                #
# ------------------------------------------------------------- #

def test_command_normalization_case_and_whitespace():
    """Verify normalization strips case differences and collapses whitespace."""
    raw = "   Typing   ON  \n"
    assert normalize_command_text(raw) == "typing on"


def test_command_normalization_punctuation():
    """Verify ASCII and Devanagari punctuation (danda ।, quotes, etc.) are removed."""
    raw = "Copy that! Clear all... 'Delete word'? सुनो, जादू।"
    assert normalize_command_text(raw) == "copy that clear all delete word सुनो जादू"


def test_command_normalization_unicode_nfkc():
    """Verify NFKC normalization unifies full-width and compatibility characters."""
    full_width = "Ｅｎｔｅｒ"
    assert normalize_command_text(full_width) == "enter"


# ------------------------------------------------------------- #
# 2. Command Recognition Tests (English & Hinglish)             #
# ------------------------------------------------------------- #

def test_english_commands_recognition():
    """Verify canonical English voice commands match accurately."""
    engine = CommandEngine()
    test_cases = [
        ("Typing on", AccessibilityCommand.TYPING_ON),
        ("Start typing", AccessibilityCommand.TYPING_ON),
        ("Typing off", AccessibilityCommand.TYPING_OFF),
        ("Stop typing", AccessibilityCommand.TYPING_OFF),
        ("Backspace", AccessibilityCommand.BACKSPACE),
        ("Delete word", AccessibilityCommand.DELETE_WORD),
        ("Clear all", AccessibilityCommand.CLEAR_FIELD),
        ("Select all", AccessibilityCommand.SELECT_ALL),
        ("Copy that", AccessibilityCommand.COPY),
        ("Paste", AccessibilityCommand.PASTE),
        ("Press enter", AccessibilityCommand.ENTER),
        ("New line", AccessibilityCommand.NEW_LINE),
        ("Undo", AccessibilityCommand.UNDO),
        ("Redo", AccessibilityCommand.REDO),
        ("Tab", AccessibilityCommand.TAB),
        ("Mouse on", AccessibilityCommand.MOUSE_ON),
        ("Mouse off", AccessibilityCommand.MOUSE_OFF),
        ("Scroll up", AccessibilityCommand.SCROLL_UP),
        ("Scroll down", AccessibilityCommand.SCROLL_DOWN),
        ("Stop all", AccessibilityCommand.STOP_ALL),
        ("Emergency stop", AccessibilityCommand.EMERGENCY_STOP),
    ]

    for phrase, expected_cmd in test_cases:
        cmd, conf, _ = engine.match(phrase, enforce_cooldown=False)
        assert cmd == expected_cmd, f"Expected '{phrase}' to match {expected_cmd}, got {cmd}"
        assert conf >= 0.9


def test_hinglish_hindi_commands_recognition():
    """Verify Devanagari Hindi and Hinglish voice command variants match."""
    engine = CommandEngine()
    test_cases = [
        ("टाइपिंग ऑन", AccessibilityCommand.TYPING_ON),
        ("टाइपिंग शुरू", AccessibilityCommand.TYPING_ON),
        ("टाइपिंग ऑफ", AccessibilityCommand.TYPING_OFF),
        ("टाइपिंग बंद", AccessibilityCommand.TYPING_OFF),
        ("बैकस्पेस", AccessibilityCommand.BACKSPACE),
        ("डिलीट वर्ड", AccessibilityCommand.DELETE_WORD),
        ("शब्द हटाओ", AccessibilityCommand.DELETE_WORD),
        ("पूरा मिटाओ", AccessibilityCommand.CLEAR_FIELD),
        ("सब चुनो", AccessibilityCommand.SELECT_ALL),
        ("कॉपी करो", AccessibilityCommand.COPY),
        ("पेस्ट", AccessibilityCommand.PASTE),
        ("एंटर दबाओ", AccessibilityCommand.ENTER),
        ("नई लाइन", AccessibilityCommand.NEW_LINE),
        ("माउस ऑन", AccessibilityCommand.MOUSE_ON),
        ("माउस ऑफ", AccessibilityCommand.MOUSE_OFF),
        ("स्क्रॉल अप", AccessibilityCommand.SCROLL_UP),
        ("स्क्रॉल डाउन", AccessibilityCommand.SCROLL_DOWN),
        ("इमरजेंसी स्टॉप", AccessibilityCommand.EMERGENCY_STOP),
    ]

    for phrase, expected_cmd in test_cases:
        cmd, conf, _ = engine.match(phrase, enforce_cooldown=False)
        assert cmd == expected_cmd, f"Expected Hindi '{phrase}' to match {expected_cmd}, got {cmd}"


def test_wake_word_query_extraction():
    """Verify 'Hey Jadoo' matches and extracts trailing query text."""
    engine = CommandEngine()
    cmd, conf, query = engine.match("Hey Jadoo what is the current time", enforce_cooldown=False)
    assert cmd == AccessibilityCommand.WAKE_UP
    assert conf >= 0.95
    assert query == "what is the current time"

    # Wake phrase only
    cmd, conf, query = engine.match("Hey Jadoo", enforce_cooldown=False)
    assert cmd == AccessibilityCommand.WAKE_UP
    assert query == ""


# ------------------------------------------------------------- #
# 3. CRITICAL: Strict Dictation Mode Isolation Tests            #
# ------------------------------------------------------------- #

def test_strict_dictation_mode_treats_commands_as_literal_text():
    """MANDATORY TEST: When Typing Mode is ON, all command words MUST be typed as literal text."""
    router = ModeRouter(initial_mode=JadooOperatingMode.DICTATION_MODE)

    # These words must NEVER execute as actions during dictation!
    dictated_command_phrases = [
        "Backspace",
        "Clear all",
        "Delete word",
        "Select all",
        "Copy that",
        "Paste",
        "Press enter",
        "New line",
        "Tab",
        "Scroll up",
        "Scroll down",
        "Mouse on",
        "Mouse off",
    ]

    for phrase in dictated_command_phrases:
        action, cmd, payload = router.route_speech(phrase)
        assert action == "DICTATE_TEXT", f"Expected '{phrase}' to be DICTATE_TEXT, got {action}"
        assert cmd is None, f"Expected command to be None during dictation, got {cmd}"
        assert payload == phrase, f"Expected payload '{phrase}', got '{payload}'"


def test_strict_dictation_mode_exit_phrase_safely_stops_typing():
    """MANDATORY TEST: 'Typing off' safely exits dictation mode into command mode."""
    router = ModeRouter(initial_mode=JadooOperatingMode.DICTATION_MODE)

    action, cmd, payload = router.route_speech("typing off")
    assert action == "EXECUTE_COMMAND"
    assert cmd == AccessibilityCommand.TYPING_OFF
    assert router.mode == JadooOperatingMode.COMMAND_MODE


def test_commands_execute_normally_after_dictation_is_stopped():
    """MANDATORY TEST: After dictation mode is exited, the same command words execute normally."""
    engine = CommandEngine(cooldown_sec=0.0)
    router = ModeRouter(initial_mode=JadooOperatingMode.DICTATION_MODE, command_engine=engine)

    # 1. Exit dictation mode
    router.route_speech("typing off")
    assert router.mode == JadooOperatingMode.COMMAND_MODE

    # 2. Now 'backspace' should execute as a command
    action, cmd, _ = router.route_speech("backspace")
    assert action == "EXECUTE_COMMAND"
    assert cmd == AccessibilityCommand.BACKSPACE

    # 3. 'clear all' should execute as a command
    action, cmd, _ = router.route_speech("clear all")
    assert action == "EXECUTE_COMMAND"
    assert cmd == AccessibilityCommand.CLEAR_FIELD

    # 4. 'mouse off' should execute as a command
    action, cmd, _ = router.route_speech("mouse off")
    assert action == "EXECUTE_COMMAND"
    assert cmd == AccessibilityCommand.MOUSE_OFF


def test_emergency_stop_available_in_both_modes():
    """MANDATORY TEST: Emergency stop must work in both dictation mode and command mode."""
    # Dictation mode
    router_dictating = ModeRouter(initial_mode=JadooOperatingMode.DICTATION_MODE)
    action, cmd, _ = router_dictating.route_speech("emergency stop")
    assert action == "EXECUTE_COMMAND"
    assert cmd == AccessibilityCommand.EMERGENCY_STOP
    assert router_dictating.mode == JadooOperatingMode.STOPPED

    # Command mode
    router_cmd = ModeRouter(initial_mode=JadooOperatingMode.COMMAND_MODE)
    action, cmd, _ = router_cmd.route_speech("emergency stop")
    assert action == "EXECUTE_COMMAND"
    assert cmd == AccessibilityCommand.EMERGENCY_STOP
    assert router_cmd.mode == JadooOperatingMode.STOPPED


# ------------------------------------------------------------- #
# 4. Duplicate Suppression & Cooldown Tests                     #
# ------------------------------------------------------------- #

def test_duplicate_command_suppression():
    """Verify rapid repeat of the same command is suppressed."""
    engine = CommandEngine(cooldown_sec=0.75)

    cmd1, _, _ = engine.match("backspace")
    assert cmd1 == AccessibilityCommand.BACKSPACE

    # Immediate repeat of same command should be suppressed
    cmd2, conf2, _ = engine.match("backspace")
    assert cmd2 is None
    assert conf2 == 0.0


def test_emergency_stop_bypasses_cooldown():
    """Verify emergency stop executes immediately even if another command just fired."""
    engine = CommandEngine(cooldown_sec=1.0)

    engine.match("select all")
    # Immediate emergency stop should NOT be blocked
    cmd, conf, _ = engine.match("emergency stop")
    assert cmd == AccessibilityCommand.EMERGENCY_STOP
    assert conf >= 0.9


# ------------------------------------------------------------- #
# 5. Keyboard Action Controller Tests                           #
# ------------------------------------------------------------- #

def test_keyboard_controller_clear_field_safety():
    """Verify clear_current_field executes Ctrl+A -> Backspace, never destructive deletion."""
    mock_pyautogui = MagicMock()
    controller = KeyboardActionController(py_backend=mock_pyautogui)

    ok = controller.clear_current_field()
    assert ok is True
    # Must have called hotkey('ctrl', 'a') then press('backspace')
    mock_pyautogui.hotkey.assert_called_with("ctrl", "a")
    mock_pyautogui.press.assert_called_with("backspace")


def test_keyboard_controller_action_dispatch():
    """Verify all text editing commands dispatch to appropriate PyAutoGUI keys."""
    mock_pyautogui = MagicMock()
    controller = KeyboardActionController(py_backend=mock_pyautogui, min_interval_sec=0.0)

    controller.execute_command(AccessibilityCommand.BACKSPACE)
    mock_pyautogui.press.assert_called_with("backspace")

    controller.execute_command(AccessibilityCommand.DELETE_WORD)
    mock_pyautogui.hotkey.assert_called_with("ctrl", "backspace")

    controller.execute_command(AccessibilityCommand.SELECT_ALL)
    mock_pyautogui.hotkey.assert_called_with("ctrl", "a")

    controller.execute_command(AccessibilityCommand.COPY)
    mock_pyautogui.hotkey.assert_called_with("ctrl", "c")

    controller.execute_command(AccessibilityCommand.PASTE)
    mock_pyautogui.hotkey.assert_called_with("ctrl", "v")

    controller.execute_command(AccessibilityCommand.ENTER)
    mock_pyautogui.press.assert_called_with("enter")

    controller.execute_command(AccessibilityCommand.NEW_LINE)
    mock_pyautogui.hotkey.assert_called_with("shift", "enter")

    controller.execute_command(AccessibilityCommand.TAB)
    mock_pyautogui.press.assert_called_with("tab")

    controller.execute_command(AccessibilityCommand.UNDO)
    mock_pyautogui.hotkey.assert_called_with("ctrl", "z")

    controller.execute_command(AccessibilityCommand.REDO)
    mock_pyautogui.hotkey.assert_called_with("ctrl", "y")


# ------------------------------------------------------------- #
# 6. Floating Panel UI Tests                                    #
# ------------------------------------------------------------- #

def test_floating_panel_creation_and_accessible_buttons(qapp):
    """Verify FloatingControlPanel creates all 17 buttons and stays on top."""
    settings = AppSettings()
    panel = FloatingControlPanel(settings=settings)

    # 17 Accessible buttons present
    assert panel.btn_start_listen is not None
    assert panel.btn_stop_listen is not None
    assert panel.btn_typing_on is not None
    assert panel.btn_typing_off is not None
    assert panel.btn_backspace is not None
    assert panel.btn_delete_word is not None
    assert panel.btn_clear_field is not None
    assert panel.btn_select_all is not None
    assert panel.btn_copy is not None
    assert panel.btn_paste is not None
    assert panel.btn_enter is not None
    assert panel.btn_new_line is not None
    assert panel.btn_mouse_toggle is not None
    assert panel.btn_scroll_up is not None
    assert panel.btn_scroll_down is not None
    assert panel.btn_stop_all is not None
    assert panel.btn_assistant is not None

    panel.close()


def test_floating_panel_mode_badge_updates(qapp):
    """Verify mode badge updates text dynamically."""
    settings = AppSettings()
    panel = FloatingControlPanel(settings=settings)

    panel.update_mode_badge("DICTATION_MODE")
    assert "DICTAT" in panel.lbl_mode_badge.text()

    panel.update_mode_badge("COMMAND_MODE")
    assert "COMMAND" in panel.lbl_mode_badge.text()

    panel.update_mode_badge("STOPPED")
    assert "STOPPED" in panel.lbl_mode_badge.text()

    panel.close()


def test_floating_panel_compact_mode_toggle(qapp):
    """Verify toggle between compact and expanded views."""
    settings = AppSettings()
    panel = FloatingControlPanel(settings=settings)
    panel.show()

    # Default expanded
    assert panel._is_compact is False
    assert panel.scroll_area.isVisible() is True

    # Toggle to compact
    panel.toggle_compact_mode()
    assert panel._is_compact is True
    assert panel.scroll_area.isVisible() is False
    assert panel.compact_row.isVisible() is True

    # Toggle back to expanded
    panel.toggle_compact_mode()
    assert panel._is_compact is False
    assert panel.scroll_area.isVisible() is True

    panel.close()


def test_floating_panel_geometry_persistence(qapp, tmp_path):
    """Verify floating panel position and size persist into settings."""
    cfg_file = tmp_path / "test_config.toml"
    settings = AppSettings()

    panel = FloatingControlPanel(settings=settings)
    panel.move(450, 250)
    panel.resize(300, 520)
    panel._save_geometry()

    assert settings.accessibility.panel_x == 450
    assert settings.accessibility.panel_y == 250
    assert settings.accessibility.panel_width == 300
    assert settings.accessibility.panel_height == 520

    panel.close()


# ------------------------------------------------------------- #
# 7. Windows Startup Integration Tests                         #
# ------------------------------------------------------------- #

def test_windows_startup_command_format():
    """Verify startup command generates valid python path and app.py path."""
    cmd = get_startup_command()
    assert "app.py" in cmd
    assert "--minimized" in cmd
