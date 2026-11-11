"""Replicate the exact except-branch path to find why persist isn't happening."""
import sys, os, time
sys.path.insert(0, r"C:\Users\Admin\HeadMouseAI")
os.chdir(r"C:\Users\Admin\HeadMouseAI")
import numpy as np
import cv2
from core.camera import CameraCapture, CameraError
from core.face_landmarker import FaceLandmarkerWrapper
from core.nose_tracker import NoseTracker
from core.eye_tracker import EyeTracker
from utils.logger import logger

class App:
    def __init__(self):
        self.camera = CameraCapture()
        self.landmarker = FaceLandmarkerWrapper()
        self.nose_tracker = NoseTracker()
        self.eye_tracker = EyeTracker()
        self.camera_ok = False
        self.error_message = None

    def run(self):
        try:
            self.camera.initialize(brightness=100, exposure=-1, focus=-1)
            self.camera_ok = True
        except CameraError as e:
            logger.error(f"Camera error: {e}")
            self.error_message = str(e)
            self.camera_ok = False
            print("CALLING fallback window")
            self._show_fallback_window()
        finally:
            self.cleanup()

    def _show_fallback_window(self):
        h, w = 720, 1280
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        cv2.putText(frame, "HEADMOUSE AI - Phase 1", (w // 2 - 460, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (90, 180, 255), 3)
        err = self.error_message or "Camera unavailable."
        cv2.putText(frame, f"No camera detected.", (80, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180,30,30), 2)
        cv2.putText(frame, f"Details: {err}", (80, 260), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (180,30,30), 2)
        cv2.imshow("HEADMOUSE AI - Phase 1: Camera & Face Detection", frame)
        print("[fallback] after imshow")
        self._persist_frame(frame)
        self.app_running = True
        while self.app_running:
            if cv2.waitKey(1) & 0xFF != 27:
                break
            self.app_running = False
        cv2.destroyAllWindows()
        print("[fallback] done")

    def _persist_frame(self, frame):
        try:
            out = r"C:\Users\Admin\HeadMouseAI\assets\screenshot_phase1.png"
            rv = cv2.imwrite(out, frame)
            print(f"[persist] rv={rv} exists={os.path.exists(out)} size={os.path.getsize(out)}")
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"[persist] FAILED: {e}")

    def cleanup(self):
        self.camera.close()
        cv2.destroyAllWindows()

a = App()
a.run()
