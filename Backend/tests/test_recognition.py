"""
Tests: recognition app — enrolment, matching, liveness, verify endpoint.
"""

import base64
import io
import numpy as np
import pytest
from unittest.mock import patch, MagicMock


# ── Matching engine unit tests ─────────────────────────────────────── #

class TestCosineDistance:
    def test_identical_vectors(self):
        from recognition.matching import cosine_distance
        v = np.array([1.0, 0.0, 0.0])
        assert cosine_distance(v, v) == pytest.approx(0.0, abs=1e-6)

    def test_orthogonal_vectors(self):
        from recognition.matching import cosine_distance
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        assert cosine_distance(a, b) == pytest.approx(1.0, abs=1e-6)

    def test_opposite_vectors(self):
        from recognition.matching import cosine_distance
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        assert cosine_distance(a, b) == pytest.approx(2.0, abs=1e-6)

    def test_zero_vector_returns_1(self):
        from recognition.matching import cosine_distance
        a = np.array([0.0, 0.0])
        b = np.array([1.0, 0.0])
        assert cosine_distance(a, b) == 1.0

    def test_similarity_is_inverse_of_distance(self):
        from recognition.matching import cosine_distance, cosine_similarity
        a = np.random.rand(128)
        b = np.random.rand(128)
        d = cosine_distance(a, b)
        s = cosine_similarity(a, b)
        assert s == pytest.approx(1.0 - d, abs=1e-6)


@pytest.mark.django_db
class TestFindBestMatch:
    def test_no_embeddings_returns_none(self):
        from recognition.matching import find_best_match
        probe = np.random.rand(4096).astype(np.float32)
        person, conf, dist = find_best_match(probe)
        assert person is None

    def test_finds_matching_person(self, face_embedding):
        from recognition.matching import find_best_match
        # Use the same vector — should match perfectly
        probe = face_embedding.get_vector()
        person, conf, dist = find_best_match(probe)
        assert person is not None
        assert person.id == face_embedding.person.id
        assert dist < 0.01  # near-zero distance for identical vector

    def test_can_scope_match_to_specific_embeddings(self, face_embedding):
        from recognition.matching import find_best_match
        from recognition.models import EnrolledPerson, FaceEmbedding

        other = EnrolledPerson.objects.create(name='Other Person', employee_id='EMP-002')
        other_embedding = FaceEmbedding(person=other)
        other_embedding.set_vector(np.array([1.0, 0.0, 0.0]))
        other_embedding.save()

        person, _, _ = find_best_match(
            face_embedding.get_vector(),
            embeddings=FaceEmbedding.objects.filter(person=other),
        )
        assert person is None

    def test_no_match_above_threshold(self, face_embedding):
        from recognition.matching import find_best_match
        # Use a perpendicular vector — should not match
        stored = face_embedding.get_vector()
        probe  = np.zeros_like(stored)
        probe[0] = 1.0  # orthogonal direction
        person, conf, dist = find_best_match(probe)
        # Distance will be high — no match returned
        assert person is None or dist > 0.1


# ── Liveness unit tests ────────────────────────────────────────────── #

class TestLiveness:
    def _make_frame(self, noise=False):
        import cv2
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        if noise:
            frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        return frame

    def test_no_frames_returns_not_live(self):
        from recognition.liveness import check_liveness
        result = check_liveness([])
        assert result.is_live is False

    def test_motion_detected_between_different_frames(self):
        from recognition.liveness import detect_motion_from_frames
        f1 = self._make_frame(noise=False)
        f2 = self._make_frame(noise=True)
        assert detect_motion_from_frames([f1, f2], pixel_threshold=100) is True

    def test_no_motion_between_identical_frames(self):
        from recognition.liveness import detect_motion_from_frames
        f = self._make_frame(noise=False)
        assert detect_motion_from_frames([f, f], pixel_threshold=100) is False

    def test_single_frame_no_motion(self):
        from recognition.liveness import detect_motion_from_frames
        f = self._make_frame()
        assert detect_motion_from_frames([f]) is False

    def test_decode_base64_frames(self):
        from recognition.liveness import decode_base64_frames
        import cv2
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        _, buf = cv2.imencode('.jpg', frame)
        b64 = base64.b64encode(buf).decode()
        frames = decode_base64_frames([b64])
        assert len(frames) == 1
        assert frames[0].shape == (100, 100, 3)

    def test_decode_invalid_base64_skipped(self):
        from recognition.liveness import decode_base64_frames
        frames = decode_base64_frames(['not-valid-base64!!!'])
        assert frames == []


# ── FaceEmbedding model tests ──────────────────────────────────────── #

@pytest.mark.django_db
class TestFaceEmbeddingModel:
    def test_set_and_get_vector(self, enrolled_person):
        from recognition.models import FaceEmbedding
        vec = np.array([1.0, 2.0, 3.0])
        emb = FaceEmbedding(person=enrolled_person)
        emb.set_vector(vec)
        emb.save()
        recovered = emb.get_vector()
        np.testing.assert_array_almost_equal(vec, recovered)

    def test_embedding_count_property(self, enrolled_person, face_embedding):
        assert enrolled_person.embedding_count == 1


# ── Enrolment API tests ────────────────────────────────────────────── #

@pytest.mark.django_db
class TestEnrolAPI:
    def _make_image_file(self):
        import cv2
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        _, buf = cv2.imencode('.jpg', frame)
        return io.BytesIO(buf.tobytes())

    @patch('recognition.views.extract_embedding')
    def test_enrol_success(self, mock_embed, admin_client):
        mock_embed.return_value = np.random.rand(4096).astype(np.float32)
        img = self._make_image_file()
        r = admin_client.post('/api/enrol/', {
            'name': 'Test Person',
            'employee_id': 'EMP-999',
            'images': img,
        }, format='multipart')
        assert r.status_code == 201
        assert r.data['embeddings_saved'] == 1

    def test_enrol_no_images_returns_400(self, admin_client):
        r = admin_client.post('/api/enrol/', {'name': 'Test Person'}, format='multipart')
        assert r.status_code == 400

    def test_enrol_missing_name_returns_400(self, admin_client):
        img = self._make_image_file()
        r = admin_client.post('/api/enrol/', {'images': img}, format='multipart')
        assert r.status_code == 400

    def test_viewer_cannot_enrol(self, viewer_client):
        r = viewer_client.post('/api/enrol/', {'name': 'X'}, format='multipart')
        assert r.status_code == 403

    def test_unauthenticated_cannot_enrol(self, api_client):
        r = api_client.post('/api/enrol/', {'name': 'X'}, format='multipart')
        assert r.status_code == 401

    @patch('recognition.views.extract_embedding')
    def test_no_face_detected_returns_422(self, mock_embed, admin_client):
        mock_embed.side_effect = ValueError('No face detected')
        img = self._make_image_file()
        r = admin_client.post('/api/enrol/', {
            'name': 'Ghost', 'images': img,
        }, format='multipart')
        assert r.status_code == 422


# ── Verify face API tests ─────────────────────────────────────────── #

@pytest.mark.django_db
class TestVerifyFaceAPI:
    def _b64_frame(self):
        import cv2
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        _, buf = cv2.imencode('.jpg', frame)
        return base64.b64encode(buf).decode()

    def test_empty_frames_returns_400(self, admin_client):
        r = admin_client.post('/api/verify-face/', {'frames': []}, format='json')
        assert r.status_code == 400

    def test_unauthenticated_returns_401(self, api_client):
        r = api_client.post('/api/verify-face/', {'frames': ['dGVzdA==']}, format='json')
        assert r.status_code == 401

    def test_viewer_can_attempt_own_face_verification(self, viewer_client):
        r = viewer_client.post('/api/verify-face/', {'frames': ['dGVzdA==']}, format='json')
        assert r.status_code == 400

    @patch('recognition.views.check_liveness')
    @patch('recognition.views.extract_embedding')
    @patch('recognition.views.find_best_match')
    def test_granted_response(self, mock_match, mock_embed, mock_liveness, admin_client, enrolled_person):
        from recognition.liveness import LivenessResult
        mock_liveness.return_value = LivenessResult(
            is_live=True, blink_detected=True, motion_detected=True
        )
        mock_embed.return_value = np.random.rand(4096).astype(np.float32)
        mock_match.return_value = (enrolled_person, 0.95, 0.05)

        frames = [self._b64_frame()] * 3
        r = admin_client.post('/api/verify-face/', {'frames': frames}, format='json')
        assert r.status_code == 200
        assert r.data['outcome'] == 'granted'
        assert r.data['confidence'] == pytest.approx(0.95, abs=0.01)

    @patch('recognition.views.check_liveness')
    def test_liveness_fail_denies(self, mock_liveness, admin_client):
        from recognition.liveness import LivenessResult
        mock_liveness.return_value = LivenessResult(
            is_live=False, blink_detected=False, motion_detected=False
        )
        frames = [self._b64_frame()] * 3
        r = admin_client.post('/api/verify-face/', {'frames': frames}, format='json')
        assert r.status_code == 200
        assert r.data['outcome'] == 'denied'
        assert r.data['reason'] == 'liveness_failed'
