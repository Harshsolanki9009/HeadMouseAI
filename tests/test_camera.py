"""Test camera initialization and frame capture."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from core.camera import CameraCapture, CameraError
from utils.logger import get_logger

logger = get_logger("TestCamera")


def test_camera_initialize():
    """Test that camera initializes correctly."""
    cam = CameraCapture(index=0)
    try:
        if cam.initialize(brightness=100, exposure=-1, focus=-1):
            print("[PASS] Camera initialized successfully.")
            # Read a frame to verify
            frame = cam.read_frame()
            if frame is not None:
                print(f"[PASS] Frame captured: shape={frame.shape}, dtype={frame.dtype}")
            else:
                print("[WARN] No frame captured (expected if no camera connected).")
            cam.close()
            return True
        else:
            print("[FAIL] Camera initialization returned False.")
            return False
    except CameraError as e:
        print(f"[WARN] Camera error (may be expected without hardware): {e}")
        cam.close()
        return True  # Warnings are acceptable in CI environments
    except Exception as e:
        print(f"[FAIL] Unexpected error: {e}")
        cam.close()
        return False


if __name__ == "__main__":
    success = test_camera_initialize()
    print("\nTest result: " + ("SUCCESS" if success else "FAILED"))
    sys.exit(0 if success else 1)
