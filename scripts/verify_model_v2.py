"""Test FaceLandmarker with the downloaded task model directly."""
import sys, os, time
sys.path.insert(0, r"C:\Users\Admin\HeadMouseAI")
os.chdir(r"C:\Users\Admin\HeadMouseAI")
from core.face_landmarker import FaceLandmarkerWrapper, FACE_LANDMARKER_MODEL_DIR
from utils.logger import logger

# Use a known-good working path (downloaded .task from earlier successful attempt)
WORK_PATH = r"C:\Users\Admin\.HeadMouseAI_assets"
print("Files in assets dirs:")
for d in [r"C:\Users\Admin\HeadMouseAI\assets\models", WORK_PATH]:
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            print(" ", os.path.join(d, f), f"{os.path.getsize(os.path.join(d,f))} bytes")

# Try the v2 approach: create wrapper with explicit model path
try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core import serial_dispatcher
    from mediapipe.tasks.python.components.containers import Landmark

    base = python.BaseOptions(model_asset_path=WORK_PATH + "/face_landmarker.tflite")
    print("BaseOptions created OK with WORK_PATH+face_landmarker.tflite")
    # Check if file exists there
    print("File exists:", os.path.isfile(WORK_PATH + "/face_landmarker.tflite"))
except Exception as e:
    print("Instantiate error:", e)
