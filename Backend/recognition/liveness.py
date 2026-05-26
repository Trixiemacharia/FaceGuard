"""
FaceGuard Liveness Detection Module
─────────────────────────────────────
Two complementary checks:
  1. Blink detection   — Eye Aspect Ratio (EAR) via dlib facial landmarks
  2. Motion detection  — Frame-diff pixel change via OpenCV

Both checks can be run independently or combined.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np

logger = logging.getLogger('recognition')


# ──────────────────────────────────────────────────────────────────────────── #
#  Data classes
# ──────────────────────────────────────────────────────────────────────────── #

@dataclass
class LivenessResult:
    is_live: bool
    blink_detected: bool
    motion_detected: bool
    ear_values: List[float] = field(default_factory=list)
    detail: str = ''


# ──────────────────────────────────────────────────────────────────────────── #
#  EAR blink detection
# ──────────────────────────────────────────────────────────────────────────── #

def _eye_aspect_ratio(eye_landmarks: np.ndarray) -> float:
    """
    Eye Aspect Ratio (EAR) = (|p2-p6| + |p3-p5|) / (2 * |p1-p4|)
    eye_landmarks: array of shape (6, 2)
    """
    A = np.linalg.norm(eye_landmarks[1] - eye_landmarks[5])
    B = np.linalg.norm(eye_landmarks[2] - eye_landmarks[4])
    C = np.linalg.norm(eye_landmarks[0] - eye_landmarks[3])
    if C == 0:
        return 0.0
    return (A + B) / (2.0 * C)


def detect_blink_from_frames(
    frames: List[np.ndarray],
    ear_threshold: float = 0.25,
    consec_frames: int = 2,
    required_blinks: int = 1,
) -> tuple[bool, List[float]]:
    """
    Detect blinks across a list of BGR frames.

    Returns:
        (blink_detected: bool, ear_values: list[float])

    Note:
        Requires dlib + shape_predictor_68_face_landmarks.dat.
        Falls back to True (liveness assumed) if dlib is unavailable.
    """
    try:
        import dlib
    except ImportError:
        logger.warning('dlib not installed — skipping EAR blink detection, assuming live.')
        return True, []

    predictor_path = 'shape_predictor_68_face_landmarks.dat'
    try:
        detector  = dlib.get_frontal_face_detector()
        predictor = dlib.shape_predictor(predictor_path)
    except RuntimeError:
        logger.warning('dlib landmark model not found — assuming live.')
        return True, []

    # dlib indices for left eye (36–41) and right eye (42–47)
    LEFT_EYE  = list(range(36, 42))
    RIGHT_EYE = list(range(42, 48))

    ear_values   = []
    below_count  = 0
    blink_count  = 0

    for frame in frames:
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = detector(gray, 0)

        if not faces:
            continue

        shape = predictor(gray, faces[0])
        coords = np.array([[shape.part(i).x, shape.part(i).y] for i in range(68)])

        left_ear  = _eye_aspect_ratio(coords[LEFT_EYE])
        right_ear = _eye_aspect_ratio(coords[RIGHT_EYE])
        ear       = (left_ear + right_ear) / 2.0
        ear_values.append(round(ear, 4))

        if ear < ear_threshold:
            below_count += 1
        elif below_count >= consec_frames:
            blink_count += 1
            below_count  = 0
        else:
            below_count = 0

    blink_detected = blink_count >= required_blinks
    logger.debug('EAR blinks=%d  required=%d  detected=%s', blink_count, required_blinks, blink_detected)
    return blink_detected, ear_values


# ──────────────────────────────────────────────────────────────────────────── #
#  Motion detection
# ──────────────────────────────────────────────────────────────────────────── #

def detect_motion_from_frames(
    frames: List[np.ndarray],
    pixel_threshold: int = 500,
) -> bool:
    """
    Detect motion by comparing consecutive grayscale frame differences.
    Returns True if any pair of frames has more than `pixel_threshold`
    changed pixels.
    """
    if len(frames) < 2:
        logger.debug('Not enough frames for motion detection.')
        return False

    for i in range(1, len(frames)):
        g1 = cv2.cvtColor(frames[i - 1], cv2.COLOR_BGR2GRAY)
        g2 = cv2.cvtColor(frames[i],     cv2.COLOR_BGR2GRAY)
        diff  = cv2.absdiff(g1, g2)
        _, th = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
        changed = cv2.countNonZero(th)

        if changed > pixel_threshold:
            logger.debug('Motion detected: %d changed pixels (threshold=%d)', changed, pixel_threshold)
            return True

    logger.debug('No significant motion detected.')
    return False


# ──────────────────────────────────────────────────────────────────────────── #
#  Combined check
# ──────────────────────────────────────────────────────────────────────────── #

def check_liveness(
    frames: List[np.ndarray],
    ear_threshold: float  = 0.25,
    consec_frames: int    = 2,
    required_blinks: int  = 1,
    motion_threshold: int = 500,
    require_both: bool    = False,
) -> LivenessResult:
    """
    Run both blink and motion checks on a list of frames.

    Args:
        frames:           List of BGR numpy frames from the camera.
        require_both:     If True, BOTH blink AND motion must pass.
                          If False (default), either one passing is enough.

    Returns:
        LivenessResult dataclass.
    """
    if not frames:
        return LivenessResult(is_live=False, blink_detected=False,
                              motion_detected=False, detail='No frames provided')

    blink_ok, ear_vals = detect_blink_from_frames(
        frames, ear_threshold, consec_frames, required_blinks
    )
    motion_ok = detect_motion_from_frames(frames, motion_threshold)

    if require_both:
        is_live = blink_ok and motion_ok
    else:
        is_live = blink_ok or motion_ok

    detail = f'blink={blink_ok}, motion={motion_ok}'
    logger.info('Liveness result: %s | %s', is_live, detail)

    return LivenessResult(
        is_live        = is_live,
        blink_detected = blink_ok,
        motion_detected= motion_ok,
        ear_values     = ear_vals,
        detail         = detail,
    )


# ──────────────────────────────────────────────────────────────────────────── #
#  Utility: decode base64 frame list
# ──────────────────────────────────────────────────────────────────────────── #

def decode_base64_frames(b64_list: List[str]) -> List[np.ndarray]:
    """
    Convert a list of base64-encoded JPEG/PNG strings to BGR numpy arrays.
    """
    import base64
    frames = []
    for b64 in b64_list:
        try:
            if ',' in b64:          # strip data-URL prefix
                b64 = b64.split(',', 1)[1]
            img_bytes = base64.b64decode(b64)
            arr = np.frombuffer(img_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is not None:
                frames.append(frame)
        except Exception as e:
            logger.warning('Failed to decode frame: %s', e)
    return frames