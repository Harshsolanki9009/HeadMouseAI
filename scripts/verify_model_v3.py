"""Direct test: instantiate FaceLandmarker from .HeadMouseAI_assets directly."""
import sys, os, time
sys.path.insert(0, r"C:\Users\Admin\HeadMouseAI")
from core.face_landmarker import FaceLandmarkerWrapper
import cv2

PATH = r"C:\Users\Admin\.HeadMouseAI_assets\face_landmarker.task"
print("File exists:", os.path.isfile(PATH))

try:
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    base = python.BaseOptions(model_asset_path=PATH)
    print("BaseOptions ok")
    opt = vision.FaceLandmarkerOptions(base_options=base, running_mode=vision.RunningMode.IMAGE, num_faces=1)
    t0 = time.time()
    lm = vision.FaceLandmarker.create_from_options(opt)
    dt = time.time() - t0
    print("SUCCESS created FaceLandmarker in", round(dt, 3), "s")
except Exception as e:
    print("ERROR:", type(e).__name__, e)
