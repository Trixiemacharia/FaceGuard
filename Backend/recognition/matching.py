"""
FaceGuard Matching Engine
─────────────────────────
Handles:
  • Embedding extraction      (DeepFace)
  • Cosine similarity search  (numpy)
  • Result packaging
"""

import logging
import numpy as np
from typing import Optional, Tuple

from django.conf import settings

logger = logging.getLogger('recognition')

# Lazy-import DeepFace to avoid long startup time when it's not needed
_deepface = None


def _get_deepface():
    global _deepface
    if _deepface is None:
        try:
            from deepface import DeepFace
            _deepface = DeepFace
        except ImportError:
            raise ImportError('deepface is not installed. Run: pip install deepface')
    return _deepface


def extract_embedding(image_path: str) -> np.ndarray:
    """
    Extract a face embedding from an image file.

    Args:
        image_path: Absolute path to the image file.

    Returns:
        1-D numpy float array (embedding vector).

    Raises:
        ValueError: If no face is detected in the image.
        RuntimeError: For other DeepFace errors.
    """
    cfg = settings.FACE_RECOGNITION
    DeepFace = _get_deepface()

    try:
        result = DeepFace.represent(
            img_path=image_path,
            model_name=cfg['MODEL'],
            detector_backend=cfg['DETECTOR_BACKEND'],
            enforce_detection=True,
        )
        embedding = np.array(result[0]['embedding'], dtype=np.float32)
        logger.debug('Embedding extracted: shape=%s', embedding.shape)
        return embedding
    except ValueError as e:
        logger.warning('No face detected in %s: %s', image_path, e)
        raise ValueError(f'No face detected: {e}') from e
    except Exception as e:
        logger.error('DeepFace.represent failed: %s', e)
        raise RuntimeError(f'Embedding extraction failed: {e}') from e


def cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine distance between two vectors (range 0–2, lower = more similar)."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return float(1.0 - np.dot(a, b) / (norm_a * norm_b))


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Return similarity score in [0, 1]; higher = more similar."""
    return max(0.0, 1.0 - cosine_distance(a, b))


def find_best_match(
    probe_embedding: np.ndarray,
) -> Tuple[Optional[object], float, float]:
    """
    Search all stored embeddings and return the best match.

    Returns:
        (EnrolledPerson | None, confidence: float, distance: float)
    """
    from recognition.models import FaceEmbedding

    cfg = settings.FACE_RECOGNITION
    threshold = cfg['MATCH_THRESHOLD']

    embeddings = FaceEmbedding.objects.select_related('person').filter(person__is_active=True)

    if not embeddings.exists():
        logger.info('No embeddings in DB to match against.')
        return None, 0.0, 1.0

    best_distance   = float('inf')
    best_person     = None

    for emb_obj in embeddings:
        stored_vec = emb_obj.get_vector()
        dist = cosine_distance(probe_embedding, stored_vec)
        if dist < best_distance:
            best_distance = dist
            best_person   = emb_obj.person

    confidence = cosine_similarity(probe_embedding,
                                   best_person.embeddings.first().get_vector()
                                   if best_person else probe_embedding)

    if best_distance > threshold:
        logger.info('No match found. Best distance=%.4f (threshold=%.4f)', best_distance, threshold)
        return None, confidence, best_distance

    logger.info('Match: %s  distance=%.4f  confidence=%.4f',
                best_person, best_distance, confidence)
    return best_person, confidence, best_distance