"""On-demand desktop screen capture for Jadoo Assistant.

Captures active desktop display only when explicitly requested by user.
Compresses image to JPEG with proportional downscaling for fast Gemini vision inference.
Never runs continuous capture or background recording.
"""

from __future__ import annotations

import base64
import io
from typing import Optional, Tuple

from PIL import Image, ImageGrab

from utils.logger import logger


class ScreenCapture:
    """Safe, on-demand screen capture utility."""

    @staticmethod
    def capture_screen_jpeg(
        max_dimension: int = 1280,
        quality: int = 75,
        max_dim: Optional[int] = None,
    ) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
        """Capture the primary display, downscale if needed, and encode to JPEG + Base64.

        Returns:
            Tuple of (jpeg_bytes, base64_string, error_message)
        """
        if max_dim is not None:
            max_dimension = max_dim
        img: Optional[Image.Image] = None

        # 1. Primary method: PIL.ImageGrab
        try:
            img = ImageGrab.grab(all_screens=False)
        except Exception as e:
            logger.debug(f"PIL.ImageGrab failed ({e}), attempting PySide6 QScreen fallback...")

        # 2. Fallback method: PySide6 primaryScreen grab
        if img is None:
            try:
                from PySide6.QtCore import QBuffer, QIODevice
                from PySide6.QtGui import QGuiApplication

                screen = QGuiApplication.primaryScreen()
                if screen:
                    pixmap = screen.grabWindow(0)
                    if not pixmap.isNull():
                        qimg = pixmap.toImage()
                        buf = QBuffer()
                        buf.open(QIODevice.OpenModeFlag.WriteOnly)
                        qimg.save(buf, "PNG")
                        png_bytes = buf.data().data()
                        buf.close()
                        img = Image.open(io.BytesIO(png_bytes))
            except Exception as e2:
                logger.warning(f"PySide6 screen grab fallback failed: {e2}")

        # 3. Native Win32 desktop grab via Vercel Labs agent-desktop
        if img is None:
            try:
                import os
                import tempfile
                from task_agent.agent_desktop_adapter import AgentDesktopAdapter

                adapter = AgentDesktopAdapter()
                if adapter.is_available():
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
                        temp_png = tf.name
                    res = adapter.screenshot(temp_png, screen_index=0)
                    if res.get("ok", False) and os.path.exists(temp_png) and os.path.getsize(temp_png) > 0:
                        img = Image.open(temp_png)
                        img.load()
                    try:
                        if os.path.exists(temp_png):
                            os.remove(temp_png)
                    except Exception:
                        pass
            except Exception as e3:
                logger.debug(f"Agent-desktop screen grab fallback failed: {e3}")

        if img is None:
            return None, None, "Unable to capture desktop screen (display DC unavailable)."

        try:
            # Convert RGBA to RGB for JPEG encoding
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Downscale proportionally if width or height exceeds max_dimension
            w, h = img.size
            if max(w, h) > max_dimension:
                scale = max_dimension / float(max(w, h))
                new_w = int(w * scale)
                new_h = int(h * scale)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            jpeg_bytes = buf.getvalue()
            b64_str = base64.b64encode(jpeg_bytes).decode("ascii")

            logger.info(f"Screen captured and compressed ({len(jpeg_bytes) // 1024} KB, size {img.size})")
            return jpeg_bytes, b64_str, None

        except Exception as e:
            err = f"Error compressing screen capture: {e}"
            logger.error(err)
            return None, None, err
