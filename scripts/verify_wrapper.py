"""Test FaceLandmarkerWrapper initializes correctly."""
import sys, os, time
sys.path.insert(0, r"C:\Users\Admin\HeadMouseAI")
from core.face_landmarker import FACE_LANDMARKER_MODEL_DIR
print("MODEL_DIR =", repr(FACE_LANDMARKER_MODEL_DIR))
print("exists:", os.path.isdir(FACE_LANDMARKER_MODEL_DIR))
print("files:", sorted(os.listdir(FACE_LANDMARKER_MODEL_DIR)))
if os.path.isdir(FACE_LANDMARKER_MODEL_DIR):
    for f in os.listdir(FACE_LANDMARKER_MODEL_DIR):
        print("  ", f, os.path.getsize(os.path.join(FACE_LANDMARKER_MODEL_DIR, f)), "bytes")

try:
    w = __import__('core.face_landmarker', fromlist=['FaceLandmarkerWrapper']).FaceLandmarkerWrapper()
    print("initialized:", w.initialized)
except Exception as e:
    print("ERROR:", type(e).__name__, e)
