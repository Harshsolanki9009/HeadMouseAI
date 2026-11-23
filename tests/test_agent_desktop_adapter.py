"""Tests for AgentDesktopAdapter."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from task_agent.agent_desktop_adapter import AgentDesktopAdapter


def test_adapter_initialization_and_discovery():
    adapter = AgentDesktopAdapter()
    assert adapter is not None
    # On this Windows machine with agent-desktop installed, it should locate the executable
    assert adapter.executable_path is not None
    assert "agent-desktop" in adapter.executable_path.lower()


def test_adapter_availability():
    adapter = AgentDesktopAdapter()
    available = adapter.is_available()
    assert available is True


def test_adapter_status_command():
    adapter = AgentDesktopAdapter()
    status = adapter.get_status()
    assert status.get("ok") is True
    data = status.get("data", {})
    assert data.get("platform") == "windows"
    assert "version" in data


def test_adapter_error_handling_when_binary_missing():
    adapter = AgentDesktopAdapter(executable_path=r"C:\non_existent_path\agent-desktop.exe")
    assert adapter.is_available() is False
    res = adapter.execute(["status"])
    assert res.get("ok") is False
    assert res.get("error", {}).get("code") == "BINARY_NOT_FOUND"


def test_adapter_parse_json_envelope():
    adapter = AgentDesktopAdapter()
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = json.dumps({"ok": True, "command": "status", "data": {"test": 123}})
    mock_proc.stderr = ""

    with patch("subprocess.run", return_value=mock_proc):
        res = adapter.execute(["status"])
        assert res.get("ok") is True
        assert res.get("data", {}).get("test") == 123


def test_adapter_methods_signature_and_args():
    adapter = AgentDesktopAdapter()
    with patch.object(adapter, "execute", return_value={"ok": True, "data": {}}) as mock_exec:
        adapter.launch_app("notepad.exe", activate=True, timeout_ms=5000)
        mock_exec.assert_called_with(["launch", "notepad.exe", "--timeout", "5000", "--activate"], timeout=10.0)

        adapter.close_app("notepad.exe", force=True)
        mock_exec.assert_called_with(["close-app", "notepad.exe", "--force"])

        adapter.mouse_move(150, 250, headed=True)
        mock_exec.assert_called_with(["--headed", "mouse-move", "--xy", "150,250"])

        adapter.hover("@ref1", headed=True)
        mock_exec.assert_called_with(["--headed", "hover", "@ref1"])

        adapter.click("@ref1", button="left", headed=True)
        mock_exec.assert_called_with(["--headed", "click", "@ref1", "--timeout-ms", "25000"], timeout=30.0)

        adapter.type_text("@ref1", "hello", headed=True, interval_ms=25)
        mock_exec.assert_called_with(["--headed", "type", "@ref1", "hello", "--interval-ms", "25"])

        adapter.set_value("@ref1", "direct value")
        mock_exec.assert_called_with(["set-value", "@ref1", "direct value", "--timeout-ms", "25000"], timeout=30.0)

        adapter.press_key("return", app_name="notepad.exe", headed=True)
        mock_exec.assert_called_with(["--headed", "press", "return", "--app", "notepad.exe"])
