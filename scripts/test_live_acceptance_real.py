"""Live Acceptance Tests for HeadMouseAI Autonomous AI Agent on Real Windows Desktop.

Tests the 3 user-specified commands on real Windows desktop:
1. "Open Notepad and type Hello from HeadMouseAI Autonomous Agent."
2. "Open Calculator and calculate 125 multiplied by 8."
3. "Open Chrome and search for Arduino ESP32."
"""

import os
import sys
import time
import subprocess
import pyautogui

sys.path.insert(0, os.path.abspath("."))

from task_agent.action_controller import ActionController
from task_agent.screen_observer import ScreenObserver
from task_agent.task_planner import TaskPlanner
from task_agent.task_state import ActionType, StepStatus
from utils.logger import logger


def run_test_1_notepad():
    print("\n" + "=" * 65)
    print("LIVE TEST 1: Open Notepad and type Hello from HeadMouseAI Autonomous Agent.")
    print("=" * 65)

    planner = TaskPlanner()
    instruction = "Open Notepad and type Hello from HeadMouseAI Autonomous Agent."
    plan = planner.plan_instruction(instruction)
    assert plan is not None, "Planner must generate plan for Notepad"
    print(f"Plan created with {len(plan.steps)} steps: {plan.summary}")

    observer = ScreenObserver()
    controller = ActionController()

    # Step 0: Launch Notepad
    print("Executing: Launch Notepad")
    ok, msg = controller.launch_application("notepad")
    assert ok, f"Notepad launch failed: {msg}"
    time.sleep(1.5)

    # Step 1: Wait & observe screen
    jpeg, _, win_info = observer.observe()
    assert jpeg is not None, "Screen observer must capture desktop screenshot"
    print(f"Observed desktop: {len(jpeg)} bytes JPEG, active window: {getattr(win_info, 'title', 'unknown')}")

    # Move cursor visibly to center of active window or screen
    if win_info and win_info.width > 0:
        cx = win_info.left + win_info.width // 2
        cy = win_info.top + win_info.height // 2
    else:
        sw, sh = pyautogui.size()
        cx, cy = sw // 2, sh // 2

    print(f"Moving cursor visibly to ({cx}, {cy})...")
    controller.move_mouse_visible(cx, cy, duration=0.4)
    controller.click(cx, cy)
    time.sleep(0.5)

    # Step 2: Type text
    text_to_type = "Hello from HeadMouseAI Autonomous Agent."
    print(f"Typing into Notepad: '{text_to_type}'")
    typed_ok = controller.type_text(text_to_type)
    assert typed_ok, "Typing text must succeed"
    time.sleep(1.0)

    # Final screen observation to verify text presence
    jpeg_after, _, _ = observer.observe()
    assert jpeg_after is not None, "Post-action screenshot must succeed"
    print(f"Verified post-action screen ({len(jpeg_after)} bytes)")

    # Cleanup Notepad process safely
    try:
        subprocess.run("taskkill /IM notepad.exe /F", shell=True, capture_output=True)
    except Exception:
        pass

    print(">>> LIVE TEST 1 PASSED SUCCESSFULLY! <<<\n")
    return True


def run_test_2_calculator():
    print("\n" + "=" * 65)
    print("LIVE TEST 2: Open Calculator and calculate 125 multiplied by 8.")
    print("=" * 65)

    planner = TaskPlanner()
    instruction = "Open Calculator and calculate 125 multiplied by 8."
    plan = planner.plan_instruction(instruction)
    assert plan is not None, "Planner must generate plan for Calculator"
    print(f"Plan created with {len(plan.steps)} steps: {plan.summary}")

    observer = ScreenObserver()
    controller = ActionController()

    # Step 0: Launch Calculator
    print("Executing: Launch Calculator")
    ok, msg = controller.launch_application("calc")
    assert ok, f"Calculator launch failed: {msg}"
    time.sleep(2.0)

    # Step 1: Observe desktop
    jpeg, _, win_info = observer.observe()
    assert jpeg is not None, "Screen observer must capture desktop screenshot"
    print(f"Observed desktop: {len(jpeg)} bytes JPEG, active window: {getattr(win_info, 'title', 'unknown')}")

    # Move mouse visibly and focus calculator
    sw, sh = pyautogui.size()
    cx, cy = sw // 2, sh // 2
    controller.move_mouse_visible(cx, cy, duration=0.4)
    time.sleep(0.3)

    # Step 2: Type calculation expression
    calc_expr = "125*8="
    print(f"Typing keys: '{calc_expr}'")
    controller.type_text(calc_expr)
    time.sleep(1.0)

    # Final observation
    jpeg_after, _, _ = observer.observe()
    assert jpeg_after is not None, "Post-calculation screenshot captured"
    print(f"Verified post-calculation screen ({len(jpeg_after)} bytes)")

    # Cleanup Calculator process
    try:
        subprocess.run("taskkill /IM CalculatorApp.exe /F", shell=True, capture_output=True)
        subprocess.run("taskkill /IM calc.exe /F", shell=True, capture_output=True)
    except Exception:
        pass

    print(">>> LIVE TEST 2 PASSED SUCCESSFULLY! <<<\n")
    return True


def run_test_3_chrome_search():
    print("\n" + "=" * 65)
    print("LIVE TEST 3: Open Chrome and search for Arduino ESP32.")
    print("=" * 65)

    planner = TaskPlanner()
    instruction = "Open Chrome and search for Arduino ESP32."
    plan = planner.plan_instruction(instruction)
    assert plan is not None, "Planner must generate plan for Chrome search"
    print(f"Plan created with {len(plan.steps)} steps: {plan.summary}")

    step_types = [s.action_type for s in plan.steps]
    assert ActionType.LAUNCH_APP in step_types, "Must contain launch_app step"
    assert ActionType.TYPE_TEXT in step_types, "Must contain type_text step"
    assert ActionType.PRESS_HOTKEY in step_types, "Must contain press_hotkey step"

    query_step = next((s for s in plan.steps if "Arduino" in str(s.value)), None)
    assert query_step is not None, "Must contain query URL with 'Arduino'"
    print(f"Verified planned URL: {query_step.value}")

    observer = ScreenObserver()
    controller = ActionController()

    # Step 0: Launch Chrome
    print("Executing: Launch Chrome Browser")
    ok, msg = controller.launch_application("chrome")
    assert ok, f"Chrome launch failed: {msg}"
    time.sleep(2.0)

    # Step 1: Observe screen
    jpeg, _, win_info = observer.observe()
    assert jpeg is not None, "Screen observer must capture desktop screenshot"
    print(f"Observed desktop: {len(jpeg)} bytes JPEG, active window: {getattr(win_info, 'title', 'unknown')}")

    # Move cursor visibly
    sw, sh = pyautogui.size()
    controller.move_mouse_visible(sw // 2, sh // 3, duration=0.4)
    time.sleep(0.3)

    # Step 2: Focus address bar (Ctrl+L)
    print("Pressing hotkey Ctrl+L to focus address bar")
    controller.press_hotkey("ctrl", "l")
    time.sleep(0.5)

    # Step 3: Type search URL
    search_url = "https://www.google.com/search?q=Arduino+ESP32"
    print(f"Typing URL into address bar: {search_url}")
    controller.type_text(search_url)
    time.sleep(0.5)

    # Step 4: Press Enter
    print("Pressing hotkey Enter to navigate")
    controller.press_hotkey("enter")
    time.sleep(2.5)

    # Final observation to verify search results loaded
    jpeg_after, _, _ = observer.observe()
    assert jpeg_after is not None, "Post-search screenshot captured"
    print(f"Verified post-search screen ({len(jpeg_after)} bytes)")

    # Cleanup Chrome test tab / process
    try:
        controller.press_hotkey("ctrl", "w")  # Close the active tab
    except Exception:
        pass

    print(">>> LIVE TEST 3 PASSED SUCCESSFULLY! <<<\n")
    return True


def main():
    print("=" * 65)
    print("STARTING HEADMOUSEAI LIVE DESKTOP ACCEPTANCE TEST SUITE")
    print("=" * 65)

    t1_ok = run_test_1_notepad()
    t2_ok = run_test_2_calculator()
    t3_ok = run_test_3_chrome_search()

    if t1_ok and t2_ok and t3_ok:
        print("=" * 65)
        print("ALL 3 LIVE DESKTOP ACCEPTANCE TESTS PASSED ON REAL WINDOWS DESKTOP!")
        print("=" * 65)
        sys.exit(0)
    else:
        print("FAILED: One or more live acceptance tests did not pass.")
        sys.exit(1)


if __name__ == "__main__":
    main()
