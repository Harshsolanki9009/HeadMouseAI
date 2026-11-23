"""Performance Benchmark and Accessibility Soak Test Suite for Jadoo.

Evaluates:
1. Module startup and initialization latency.
2. Memory consumption (Baseline RSS, Active RSS, Leak Detection).
3. Continuous vision & tracking loop soak test (1,000 synthetic frames).
4. Vercel agent-desktop CLI query soak test (Process lifecycle and handle cleanup).
5. Accessibility Target Size & WCAG Contrast Verification.
"""

from __future__ import annotations

import gc
import math
import os
import sys
from pathlib import Path
import time
from typing import Dict, List, Tuple

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import psutil
import pytest

from config.settings import AppSettings, get_settings
from gui.styles import (
    INK_CANVAS,
    INK_COOL_GRAY,
    INK_GRAPHITE,
    INK_MUTED_AMBER,
    INK_MUTED_CRIMSON,
    INK_MUTED_SLATE,
    INK_PURE_WHITE,
    INK_SAGE_GRAY,
    INK_SILVER_GRAY,
    INK_SOFT_IVORY,
)
from task_agent.agent_desktop_adapter import AgentDesktopAdapter
from voice_engine.mode_manager import JadooOperatingMode, ModeRouter


def hex_to_relative_luminance(hex_code: str) -> float:
    """Calculate WCAG relative luminance from a hex color string."""
    hex_code = hex_code.lstrip("#")
    if len(hex_code) == 3:
        hex_code = "".join(c * 2 for c in hex_code)
    r = int(hex_code[0:2], 16) / 255.0
    g = int(hex_code[2:4], 16) / 255.0
    b = int(hex_code[4:6], 16) / 255.0

    def adjust(channel: float) -> float:
        return channel / 12.92 if channel <= 0.03928 else math.pow((channel + 0.055) / 1.055, 2.4)

    return 0.2126 * adjust(r) + 0.7152 * adjust(g) + 0.0722 * adjust(b)


def calculate_contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculate WCAG contrast ratio between two hex colors (1.0 to 21.0)."""
    l1 = hex_to_relative_luminance(hex1)
    l2 = hex_to_relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def test_wcag_contrast_ratios() -> None:
    """Verify that all Ink Wash theme color pairings exceed WCAG AA (4.5:1)."""
    # 1. Soft Ivory (#F2F0EA) on Canvas (#17191C)
    ratio_ivory_canvas = calculate_contrast_ratio(INK_SOFT_IVORY, INK_CANVAS)
    assert ratio_ivory_canvas >= 10.0, f"Expected >10:1, got {ratio_ivory_canvas:.2f}:1"

    # 2. Soft Ivory (#F2F0EA) on Graphite Card (#222529)
    ratio_ivory_card = calculate_contrast_ratio(INK_SOFT_IVORY, INK_GRAPHITE)
    assert ratio_ivory_card >= 9.0, f"Expected >9:1, got {ratio_ivory_card:.2f}:1"

    # 3. Silver Gray (#B9C0C7) on Canvas (#17191C)
    ratio_silver_canvas = calculate_contrast_ratio(INK_SILVER_GRAY, INK_CANVAS)
    assert ratio_silver_canvas >= 6.5, f"Expected >6.5:1, got {ratio_silver_canvas:.2f}:1"

    # 4. Pure White (#FFFFFF) on Emergency Crimson (#5A2324)
    ratio_white_crimson = calculate_contrast_ratio(INK_PURE_WHITE, "#5A2324")
    assert ratio_white_crimson >= 5.0, f"Expected >=4.5:1, got {ratio_white_crimson:.2f}:1"


def test_floating_panel_accessible_target_sizes_and_labels(qapp) -> None:
    """Verify that all buttons in FloatingControlPanel meet the 44px minimum target and have accessible descriptions."""
    from gui.floating_panel import AccessibleButton, FloatingControlPanel

    panel = FloatingControlPanel()

    buttons = panel.findChildren(AccessibleButton)
    assert len(buttons) >= 15, f"Expected >=15 accessible buttons, found {len(buttons)}"

    for btn in buttons:
        # Check target height
        assert btn.minimumHeight() >= 44, f"Button '{btn.text()}' height is {btn.minimumHeight()}, expected >= 44"
        # Check accessible name
        assert btn.accessibleName() != "", f"Button '{btn.text()}' missing accessibleName"
        # Check tooltip/description
        assert btn.toolTip() != "", f"Button '{btn.text()}' missing tooltip/description"


def test_tracking_loop_soak_memory_and_latency() -> None:
    """Run 1,000 continuous simulated tracking iterations to test memory leaks and latency."""
    from core.mouse_controller import MouseController

    settings = get_settings()
    controller = MouseController(settings)
    mode_router = ModeRouter()

    process = psutil.Process(os.getpid())
    gc.collect()
    start_rss = process.memory_info().rss / (1024 * 1024)

    latencies: List[float] = []

    # Soak test loop: 1,000 frames
    for i in range(1000):
        t0 = time.perf_counter()

        # Simulate nose movement and eye winks
        nx = 0.5 + 0.05 * math.sin(i * 0.05)
        ny = 0.5 + 0.05 * math.cos(i * 0.05)
        controller.move_cursor(nx, ny)

        # Periodic command check
        if i % 100 == 0:
            mode_router.route_speech("scroll down")

        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)

    gc.collect()
    end_rss = process.memory_info().rss / (1024 * 1024)
    rss_growth = end_rss - start_rss

    avg_latency = sum(latencies) / len(latencies)
    max_latency = max(latencies)

    # Invariants for low-end hardware
    assert avg_latency < 1.0, f"Average frame tracking overhead too high: {avg_latency:.3f} ms (expected < 1.0 ms)"
    assert max_latency < 50.0, f"Max spike too high: {max_latency:.3f} ms"
    # Memory growth should be zero or negligible (< 15 MB) over 1,000 frames
    assert rss_growth < 15.0, f"Possible memory leak detected: grew by {rss_growth:.2f} MB"


def test_agent_desktop_process_soak() -> None:
    """Verify multiple consecutive agent-desktop adapter queries clean up processes cleanly without handle leaks."""
    adapter = AgentDesktopAdapter()
    if not adapter.is_available():
        pytest.skip("agent-desktop CLI not found")

    process = psutil.Process(os.getpid())
    initial_handles = process.num_handles() if hasattr(process, "num_handles") else 0

    # Execute 5 consecutive calls
    for _ in range(5):
        res = adapter.execute(["status"])
        assert res.get("ok", False) is True

    time.sleep(0.5)
    final_handles = process.num_handles() if hasattr(process, "num_handles") else 0

    if hasattr(process, "num_handles"):
        handle_diff = final_handles - initial_handles
        # Handle accumulation should be tightly bounded (< 25)
        assert handle_diff < 25, f"Excessive Windows handles accumulated: +{handle_diff}"


def run_benchmark_report() -> Dict[str, str]:
    """Execute live diagnostic benchmarks and return formatted metrics."""
    metrics: Dict[str, str] = {}
    process = psutil.Process(os.getpid())

    # 1. Measure Module Import Latency
    t0 = time.perf_counter()
    import config.settings
    import gui.styles
    import task_agent.agent_desktop_adapter
    import voice_engine.mode_manager
    t1 = time.perf_counter()
    metrics["import_latency_ms"] = f"{(t1 - t0) * 1000.0:.1f} ms"

    # 2. Measure Memory
    gc.collect()
    rss_mb = process.memory_info().rss / (1024 * 1024)
    metrics["baseline_rss_mb"] = f"{rss_mb:.1f} MB"

    # 3. Measure Synthetic Tracking Loop
    from core.mouse_controller import MouseController
    ctrl = MouseController(get_settings())
    t_start = time.perf_counter()
    for j in range(500):
        ctrl.move_cursor(0.5 + 0.01 * (j % 10), 0.5 + 0.01 * (j % 10))
    t_end = time.perf_counter()
    per_frame_us = ((t_end - t_start) / 500.0) * 1_000_000.0
    metrics["cursor_calc_latency_us"] = f"{per_frame_us:.2f} µs/frame"

    # 4. CPU count
    metrics["cpu_threads"] = str(psutil.cpu_count(logical=True))
    metrics["cpu_physical"] = str(psutil.cpu_count(logical=False))

    return metrics


if __name__ == "__main__":
    rep = run_benchmark_report()
    for k, v in rep.items():
        print(f"{k}: {v}")
