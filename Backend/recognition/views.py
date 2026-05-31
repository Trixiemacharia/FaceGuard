"""
Recognition API Views
─────────────────────
POST /api/enrol/        — store face embedding in DB
POST /api/verify-face/  — full pipeline: frame → embed → match → result
GET  /api/persons/      — list enrolled persons
"""

import logging
import os
import tempfile

from django.conf import settings
from rest_framework import generics, permissions, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .liveness import check_liveness, decode_base64_frames
from .matching import extract_embedding, find_best_match
from .models import EnrolledPerson, FaceEmbedding, VerificationLog
from .serializers import (
    EnrolledPersonSerializer,
    EnrolmentSerializer,
    VerifyFaceSerializer,
    VerificationLogSerializer,
)

logger = logging.getLogger('recognition')


# ─────────────────────────────── #
#  Permissions helpers
# ─────────────────────────────── #

class IsAdminOrGuard(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ('admin', 'guard')


# ─────────────────────────────── #
#  Enrolment
# ─────────────────────────────── #

class EnrolView(APIView):
    """
    POST /api/enrol/
    Body (multipart): name, employee_id, department, images[] (1-5 files)
    Stores an embedding for each uploaded face image.
    """
    parser_classes     = [MultiPartParser, FormParser]
    permission_classes = [IsAdminOrGuard]

    def post(self, request):
        serializer = EnrolmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data   = serializer.validated_data
        images = request.FILES.getlist('images')

        if not images:
            return Response({'error': 'At least one image is required.'}, status=status.HTTP_400_BAD_REQUEST)

        max_images = settings.FACE_RECOGNITION['MAX_ENROL_IMAGES']
        if len(images) > max_images:
            return Response(
                {'error': f'Maximum {max_images} images allowed per enrolment.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create or update the person record
        person, created = EnrolledPerson.objects.get_or_create(
            employee_id = data.get('employee_id') or None,
            defaults    = {
                'name':        data['name'],
                'department':  data.get('department', ''),
                'enrolled_by': request.user,
                'notes':       data.get('notes', ''),
            },
        )
        if not created:
            person.name       = data['name']
            person.department = data.get('department', person.department)
            person.save()

        embeddings_saved = 0
        errors           = []

        for img_file in images:
            # Write to a temp file because DeepFace needs a path
            suffix = os.path.splitext(img_file.name)[1] or '.jpg'
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in img_file.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            try:
                vector = extract_embedding(tmp_path)
                emb    = FaceEmbedding(person=person, model_name=settings.FACE_RECOGNITION['MODEL'])
                emb.set_vector(vector)
                emb.image.save(img_file.name, img_file, save=False)
                emb.save()
                embeddings_saved += 1
            except (ValueError, RuntimeError) as e:
                errors.append({'file': img_file.name, 'error': str(e)})
            finally:
                os.unlink(tmp_path)

        if embeddings_saved == 0:
            person.delete()
            return Response(
                {'error': 'No valid faces found in uploaded images.', 'details': errors},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        return Response({
            'person_id':        person.id,
            'name':             person.name,
            'embeddings_saved': embeddings_saved,
            'errors':           errors,
            'created':          created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


# ─────────────────────────────── #
#  Verification — full pipeline
# ─────────────────────────────── #

class VerifyFaceView(APIView):
    """
    POST /api/verify-face/
    Body (JSON):
        frames     : list[str]  — base64-encoded JPEG frames (≥ 3 recommended)
        camera_id  : str        — optional camera identifier
    """
    parser_classes     = [JSONParser]
    permission_classes = [IsAdminOrGuard]

    def post(self, request):
        serializer = VerifyFaceSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        b64_frames = serializer.validated_data['frames']
        camera_id  = serializer.validated_data.get('camera_id', '')
        cfg        = settings.FACE_RECOGNITION

        # 1. Decode frames
        frames = decode_base64_frames(b64_frames)
        if not frames:
            return Response({'error': 'No decodable frames provided.'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. Liveness check
        liveness = check_liveness(
            frames,
            ear_threshold   = cfg['LIVENESS']['EAR_THRESHOLD'],
            consec_frames   = cfg['LIVENESS']['EAR_CONSEC_FRAMES'],
            required_blinks = cfg['LIVENESS']['REQUIRED_BLINKS'],
            motion_threshold= cfg['LIVENESS']['MOTION_THRESHOLD'],
        )

        if not liveness.is_live:
            VerificationLog.objects.create(
                outcome       = VerificationLog.Outcome.DENIED,
                liveness_pass = False,
                camera_id     = camera_id,
                requested_by  = request.user,
                error_detail  = 'Liveness check failed',
            )
            return Response({
                'outcome':   'denied',
                'reason':    'liveness_failed',
                'detail':    liveness.detail,
                'liveness':  {'passed': False, **liveness.__dict__},
            }, status=status.HTTP_200_OK)

        # 3. Extract embedding from the middle frame (most stable)
        probe_frame = frames[len(frames) // 2]
        import cv2, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp:
            cv2.imwrite(tmp.name, probe_frame)
            tmp_path = tmp.name

        try:
            probe_vector = extract_embedding(tmp_path)
        except (ValueError, RuntimeError) as e:
            os.unlink(tmp_path)
            VerificationLog.objects.create(
                outcome      = VerificationLog.Outcome.ERROR,
                camera_id    = camera_id,
                requested_by = request.user,
                error_detail = str(e),
            )
            return Response({'outcome': 'error', 'detail': str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        # 4. Match against DB
        person, confidence, distance = find_best_match(probe_vector)
        outcome = (
            VerificationLog.Outcome.GRANTED
            if person and confidence >= cfg['CONFIDENCE_THRESHOLD']
            else VerificationLog.Outcome.DENIED
        )

        # 5. Persist log
        VerificationLog.objects.create(
            matched_person = person,
            outcome        = outcome,
            confidence     = confidence,
            distance       = distance,
            liveness_pass  = True,
            camera_id      = camera_id,
            requested_by   = request.user,
        )

        response_data = {
            'outcome':    outcome,
            'confidence': round(confidence, 4),
            'distance':   round(distance, 4),
            'liveness':   {'passed': True, **liveness.__dict__},
        }
        if person:
            response_data['person'] = {
                'id':          person.id,
                'name':        person.name,
                'employee_id': person.employee_id,
                'department':  person.department,
            }

        return Response(response_data, status=status.HTTP_200_OK)


# ─────────────────────────────── #
#  Enrolled persons list / detail
# ─────────────────────────────── #

class PersonListView(generics.ListAPIView):
    queryset           = EnrolledPerson.objects.filter(is_active=True)
    serializer_class   = EnrolledPersonSerializer
    permission_classes = [permissions.IsAuthenticated]


class PersonDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset           = EnrolledPerson.objects.all()
    serializer_class   = EnrolledPersonSerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.IsAuthenticated()]
        if self.request.method == 'DELETE':
            return [permissions.IsAdminUser()]
        return [IsAdminOrGuard()]


class VerificationLogListView(generics.ListAPIView):
    queryset           = VerificationLog.objects.all()
    serializer_class   = VerificationLogSerializer
    permission_classes = [permissions.IsAuthenticated]
