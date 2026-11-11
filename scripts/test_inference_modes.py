"""Compare MediaPipe FaceLandmarker RunningMode.IMAGE vs RunningMode.VIDEO."""

import os
import sys
import time
import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from mediapipe import tasks
from mediapipe.tasks.python import vision
import mediapipe as mp
from utils.resource import get_model_path
from core.camera import CameraCapture


def test_modes(num_frames: int = 50):
    cam = CameraCapture(0, 640, 480)
    if not cam.initialize():
        print("Camera failed")
        return

    frames = []
    for _ in range(num_frames):
        f = cam.read_frame()
        if f is not None:
            frames.append(cv2.flip(f, 1))
    cam.close()
    print(f"Captured {len(frames)} frames for comparison.")

    model_path = str(get_model_path("face_landmarker.task"))
    base_options = tasks.BaseOptions(model_asset_path=model_path)

    # Mode 1: IMAGE
    options_image = vision.FaceLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.IMAGE,
        num_faces=1,
        min_face_detection_confidence=0.35,
        min_face_presence_confidence=0.35,
        min_tracking_confidence=0.35,
        output_face_blendshapes=False,
    )
    solver_image = vision.FaceLandmarker.create_from_options(options_image)

    # Warmup
    for _ in range(5):
        rgb = cv2.cvtColor(frames[0], cv2.COLOR_BGR2RGB)
        solver_image.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))

    times_image = []
    for f in frames:
        t0 = time.perf_counter()
        rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
        res = solver_image.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))
        times_image.append((time.perf_counter() - t0) * 1000.0)

    # Mode 2: VIDEO
    options_video = vision.FaceLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        min_face_detection_confidence=0.35,
        min_face_presence_confidence=0.35,
        min_tracking_confidence=0.35,
        output_face_blendshapes=False,
    )
    solver_video = vision.FaceLandmarker.create_from_options(options_video)

    times_video = []
    ts = 0
    for f in frames:
        t0 = time.perf_counter()
        rgb = cv2.cvtColor(f, cv2.COLOR_BGR2RGB)
        ts += 33
        res = solver_video.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)
        times_video.append((time.perf_counter() - t0) * 1000.0)

    print(f"IMAGE Mode: avg {np.mean(times_image):.2f} ms (p95: {np.percentile(times_image, 95):.2f} ms)")
    print(f"VIDEO Mode: avg {np.mean(times_video):.2f} ms (p95: {np.percentile(times_video, 95):.2f} ms)")


if __name__ == "__main__":
    test_modes(50)
