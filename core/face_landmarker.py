"""Face landmark detection using MediaPipe tasks API (v1.2.2).

Wraps mediapipe.tasks.vision.FaceLandmarker for reliable facial landmark extraction
including nose tip, left eye, right eye, etc.

IMPORTANT: This project explicitly does NOT use pupil or iris coordinates
for cursor control. Only nose tip and eye landmarks are used.
"""

from __future__ import annotations

import logging
import os
import urllib.request
from typing import Any, Optional, Tuple

import cv2
import numpy as np
import mediapipe as mp
from mediapipe import tasks
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core import serial_dispatcher
from mediapipe.tasks.python.core import async_result_dispatcher
from mediapipe.tasks.python.components.containers import Landmark
from utils.logger import logger
from utils.resource import get_model_path, get_resource_path

# Face landmark indices - MediaPipe face mesh has 468 points
# Key indices used by this project:
NOSE_TIP = 1   # Nose tip
LEFT_EYE_CENTER = 33        # Left eye center
RIGHT_EYE_CENTER = 160      # Right eye center

# Default model URL for downloading the Face Landmark TFLite model
FACE_LANDMARKER_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float32/1/face_landmarker.tflite"
)
FACE_LANDMARKER_MODEL_DIR = str(get_resource_path(os.path.join("assets", "models")))


class FaceLandmarkerWrapper:
    """Wraps mediapipe FaceLandmarker for reliable facial landmark extraction."""

    def __init__(self, confidence_threshold: float = 0.35) -> None:
        self.confidence_threshold = float(confidence_threshold)
        self.initialized = False
        try:
            model_file = get_model_path("face_landmarker.task")
            if not model_file.is_file():
                self._ensure_model()
                model_file = get_model_path("face_landmarker.task")
            model_path = str(model_file)
            base_options = tasks.BaseOptions(model_asset_path=model_path)
            # Use responsive confidence thresholds
            det_conf = max(0.2, self.confidence_threshold)
            options = vision.FaceLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=det_conf,
                min_face_presence_confidence=det_conf,
                min_tracking_confidence=det_conf,
                output_face_blendshapes=False,
                output_facial_transformation_matrixes=False,
            )
            self._solver = vision.FaceLandmarker.create_from_options(options)
            self.initialized = True
            logger.info(f"FaceLandmark initialized. Model at {model_path} (confidence={det_conf})")
        except Exception as e:
            logger.error(f"Failed to initialize FaceLandmarker: {e}")
            raise

    def _ensure_model(self) -> None:
        """Download the face landmarker model TFLite file if missing."""
        if os.path.exists(FACE_LANDMARKER_MODEL_DIR):
            return
        try:
            os.makedirs(FACE_LANDMARKER_MODEL_DIR, exist_ok=True)
            dest = os.path.join(FACE_LANDMARKER_MODEL_DIR, "face_landmarker.tflite")
            if not os.path.exists(dest):
                filename = FACE_LANDMARKER_MODEL_URL.split("/")[-1]
                url = FACE_LANDMARKER_MODEL_URL
                logger.info(f"Downloading {url} to {dest}...")
                urllib.request.urlretrieve(url, dest)
                logger.info("Model download complete.")
            else:
                logger.debug("Model already present.")
        except Exception as e:
            logger.error(f"Could not download face landmarker model: {e}")
            raise

    def detect_landmarks(
        self,
        frame: np.ndarray,
        confidence_threshold: Optional[float] = None,
        is_rgb: bool = False,
    ) -> dict[str, Any]:
        """Detect facial landmarks on a frame.

        Args:
            frame: Frame from camera (HxWx3, uint8) in BGR (default) or RGB format.
            confidence_threshold: Minimum visibility/presence to consider detected.
            is_rgb: If True, skips redundant BGR->RGB conversion.

        Returns:
            Dictionary with detected landmarks:
            {
                "has_face": bool,
                "landmarks": [[x, y, z, visibility, presence], ...],  # normalized 0-1
                "nose": (x, y, visibility) or None,
                "left_eye": (x, y, visibility) or None,
                "right_eye": (x, y, visibility) or None,
            }
        """
        threshold = self.confidence_threshold if confidence_threshold is None else confidence_threshold

        if not self.initialized:
            return {"has_face": False, "landmarks": [], "nose": None, "left_eye": None, "right_eye": None}

        if frame is None or frame.size == 0:
            return {"has_face": False, "landmarks": [], "nose": None, "left_eye": None, "right_eye": None}

        try:
            rgb = frame if is_rgb else cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self._solver.detect(mp_image)

            if result is None or len(result.face_landmarks) == 0:
                return {"has_face": False, "landmarks": [], "nose": None, "left_eye": None, "right_eye": None}

            face_lm = result.face_landmarks[0]
            # Fast extraction avoiding redundant float conversions
            full_landmarks = [
                [
                    lm.x,
                    lm.y,
                    lm.z,
                    100 if lm.visibility is None else int(lm.visibility * 100),
                    100 if lm.presence is None else int(lm.presence * 100),
                ]
                for lm in face_lm
            ]

            key_data = {
                "nose": (full_landmarks[NOSE_TIP][0], full_landmarks[NOSE_TIP][1], full_landmarks[NOSE_TIP][3])
                if len(full_landmarks) > NOSE_TIP else None,
                "left_eye": (full_landmarks[LEFT_EYE_CENTER][0], full_landmarks[LEFT_EYE_CENTER][1], full_landmarks[LEFT_EYE_CENTER][3])
                if len(full_landmarks) > LEFT_EYE_CENTER else None,
                "right_eye": (full_landmarks[RIGHT_EYE_CENTER][0], full_landmarks[RIGHT_EYE_CENTER][1], full_landmarks[RIGHT_EYE_CENTER][3])
                if len(full_landmarks) > RIGHT_EYE_CENTER else None,
            }

            return {
                "has_face": True,
                "landmarks": full_landmarks,
                "nose": key_data["nose"],
                "left_eye": key_data["left_eye"],
                "right_eye": key_data["right_eye"],
                "confidence": threshold,
            }

        except Exception as e:
            logger.debug(f"Landmark detection error: {e}")
            return {"has_face": False, "landmarks": [], "nose": None,
                    "left_eye": None, "right_eye": None, "error": str(e)}


class EyeARCalculator:
    """Calculates Eye Aspect Ratio (EAR) directly from raw landmark lists.

    Formula: EAR = (|p1-p4| + |p2-p5|) / (2 * |p3-p6|)
    Where:
      p1 = left_eye_outer_corner (idx 36)
      p2 = left_eye_left_corner (idx 240)
      p3 = left_eye_center (idx 33)
      p4 = left_eye_inner_corner (idx 133)
      p5 = right_eye_inner_corner (idx 51)
      p6 = right_eye_outer_corner (idx 370)
    """

    REQUIRED_INDICES = {36, 240, 33, 133, 51, 370}

    @staticmethod
    def calculate_ear(points: list[list]) -> float | None:
        """Calculate EAR from a flat list of [x, y, z, vis, pres].

        Args:
            points: Flat list containing landmarks at indices 36, 240, 33, 133, 51, 370.

        Returns:
            EAR value between 0 and 1, or None if insufficient data.
        """
        if len(points) < max(EyeARCalculator.REQUIRED_INDICES) + 1:
            return None

        try:
            pt_1 = (float(points[36][0]), float(points[36][1]))
            pt_2 = (float(points[240][0]), float(points[240][1]))
            pt_3 = (float(points[33][0]), float(points[33][1]))
            pt_4 = (float(points[133][0]), float(points[133][1]))
            pt_5 = (float(points[51][0]), float(points[51][1]))
            pt_6 = (float(points[370][0]), float(points[370][1]))

            a = sum((u - v) ** 2 for u, v in [(pt_1, pt_3)] * 1 + [(pt_4, pt_3)] * 1 + [(pt_2, pt_5)] * 1 + [(pt_3, pt_6)] * 1) ** 0.5 \
                if False else 0.0

            # Simpler approach: compute pair norms separately
            d1 = ((pt_1[0] - pt_4[0]) ** 2 + (pt_1[1] - pt_4[1]) ** 2) ** 0.5
            d2 = ((pt_2[0] - pt_5[0]) ** 2 + (pt_2[1] - pt_5[1]) ** 2) ** 0.5
            d3 = ((pt_3[0] - pt_6[0]) ** 2 + (pt_3[1] - pt_6[1]) ** 2) ** 0.5

            denom = max(d3, 0.01)
            ear = (d1 + d2) / denom
            ear = max(0.0, min(1.0, ear))
            return float(ear)
        except Exception:
            return None


