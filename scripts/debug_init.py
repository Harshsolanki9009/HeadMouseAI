"""Debug: replicate wrapper logic to see exact path used."""
import sys, os, time
sys.path.insert(0, r"C:\Users\Admin\HeadMouseAI")
os.chdir(r"C:\Users\Admin\HeadMouseAI")

# Replicate wrapper init exactly
import mediapipe as mp
from mediapipe import tasks
from mediapipe.tasks.python import vision

print("current dir:", os.getcwd())
print("FACE_LANDMARKER_MODEL_DIR:", r"C:\Users\Admin\.HeadMouseAI_assets")
p = r"C:\Users\Admin\.HeadMouseAI_assets"
print("exists:", os.path.isfile(p + "/face_landmarker.task"))
print("read bytes:", os.path.getsize(p + "/face_landmarker.task"))

base_options = tasks.BaseOptions(model_asset_path=p + "/face_landmarker.task")
print("BaseOptions created with task path")
opt = vision.FaceLandmarkerOptions(
    base_options=base_options,
    running_mode=vision.RunningMode.IMAGE,
    num_faces=1,
)
try:
    lm = vision.FaceLandmarker.create_from_options(opt)
    print("SUCCESS")
except Exception as e:
    print("FAIL:", type(e).__name__, e)
