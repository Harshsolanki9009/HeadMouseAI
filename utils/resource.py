"""Resource resolution utility for development and frozen PyInstaller standalone execution.

Ensures assets, models, configuration files, and icons are found seamlessly
whether running from source or within a packaged desktop distribution.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Project root directory when running from source
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def get_base_path() -> Path:
    """Return the runtime base directory for assets.

    - In PyInstaller onefile mode: sys._MEIPASS
    - In PyInstaller onedir mode: directory containing the executable
    - In development mode: project root directory
    """
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS)
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def get_resource_path(relative_path: str | Path) -> Path:
    """Resolve a relative resource path against the runtime base directory.

    Args:
        relative_path: Subpath relative to application root (e.g. 'assets/models/face_landmarker.task')

    Returns:
        Absolute Path object.
    """
    base = get_base_path()
    resolved = (base / relative_path).resolve()
    return resolved


def get_model_path(model_filename: str = "face_landmarker.task") -> Path:
    """Locate the MediaPipe face landmark model file.

    Checks prioritized locations:
    1. Runtime bundled assets/models/
    2. Project assets/models_tmp/
    3. User profile ~/.HeadMouseAI_assets/ (legacy fallback)
    """
    # 1. Bundled assets location
    p1 = get_resource_path(Path("assets") / "models" / model_filename)
    if p1.is_file():
        return p1

    # 2. Alternative tflite extension
    if model_filename.endswith(".task"):
        alt_tflite = model_filename.replace(".task", ".tflite")
        p1_alt = get_resource_path(Path("assets") / "models" / alt_tflite)
        if p1_alt.is_file():
            return p1_alt

    # 3. Development assets_tmp location
    p2 = get_resource_path(Path("assets") / "models_tmp" / model_filename)
    if p2.is_file():
        return p2

    # 4. User profile legacy location
    legacy_dir = Path.home() / ".HeadMouseAI_assets"
    p3 = legacy_dir / model_filename
    if p3.is_file():
        return p3

    # Fallback default
    return p1


def get_config_path(config_name: str = "config.toml") -> Path:
    """Locate config.toml, prioritizing user editable file next to executable."""
    if getattr(sys, "frozen", False):
        exe_dir_cfg = Path(sys.executable).resolve().parent / config_name
        if exe_dir_cfg.is_file():
            return exe_dir_cfg
    return get_resource_path(config_name)


def get_icon_path(icon_name: str = "app_icon.png") -> Path:
    """Return path to application icon."""
    return get_resource_path(Path("assets") / "icons" / icon_name)


def get_image_path(image_name: str) -> Path:
    """Return path to image asset."""
    return get_resource_path(Path("assets") / "images" / image_name)
