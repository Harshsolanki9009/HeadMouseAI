"""Verify FaceLandmarker loads with downloaded model, then run main app briefly."""
import sys
sys.path.insert(0, r"C:\Users\Admin\HeadMouseAI")
import os
os.chdir(r"C:\Users\Admin\HeadMouseAI")  # ensure models dir is writable
from core.face_landmarker import FaceLandmarkerWrapper, FACE_LANDMARKER_MODEL_DIR
from utils.logger import logger
import numpy as np
import cv2
import time

logger.info(f"Model dir: {FACE_LANDMARKER_MODEL_DIR}")
print("Files:", sorted(os.listdir(FACE_LANDMARKER_MODEL_DIR)))

wrapper = FaceLandmarkerWrapper()
if not wrapper.initialized:
    print("FAIL: wrapper not initialized.")
    sys.exit(1)
print("SUCCESS: FaceLandmarker initialized.")

cap = cv2.VideoCapture(0)
if cap.isOpened():
    ret, frame = cap.read()
    if ret:
        t0 = time.time()
        result = wrapper.detect_landmarks(frame)
        dt = time.time() - t0
        print(f"detect took {dt:.3f}s, has_face={result.get('has_face')}, "
              f"nose={result.get('nose')}")
    cap.release()
else:
    print("No camera; model loads OK. Will try live app path next.")

print("OK")
