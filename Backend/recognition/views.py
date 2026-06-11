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
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .liveness import check_liveness, decode_base64_frames
from .matching import extract_embedding, find_best_match
from .models import EnrolledPerson, FaceEmbedding, VerificationLog
from .serializers import (
    EnrolledPersonSerializer,
    EnrolmentSerializer,
    SelfEnrolmentSerializer,
    VerifyFaceSerializer,
    VerificationLogSerializer,
)
from users.serializers import UserSerializer

logger = logging.getLogger('recognition')


def _split_name(full_name):
    parts = full_name.strip().split()
    first_name = parts[0] if parts else ''
    last_name = ' '.join(parts[1:]) if len(parts) > 1 else first_name
    return first_name, last_name


def _record_zone_event(*, user, person, outcome, confidence=0.0, camera_id='', liveness_pass=False, reason=''):
    try:
        from zones.models import AccessEvent
        AccessEvent.objects.create(
            user=user if getattr(user, 'is_authenticated', False) else None,
            person=person,
            outcome=outcome,
            confidence=confidence,
            camera_id=camera_id,
            liveness_pass=liveness_pass,
            denial_reason=reason,
        )
    except Exception as exc:
        logger.warning('Failed to record zone access event: %s', exc)


def _flag_repeated_failures(user, camera_id):
    if not getattr(user, 'is_authenticated', False):
        return

    window_start = timezone.now() - timezone.timedelta(minutes=15)
    failures = VerificationLog.objects.filter(
        requested_by=user,
        outcome=VerificationLog.Outcome.DENIED,
        created_at__gte=window_start,
    ).count()

    if failures < 3:
        return

    try:
        from alerts.models import Alert
        recent_alert = Alert.objects.filter(
            alert_type=Alert.AlertType.MULTIPLE_FAIL,
            camera_id=camera_id or 'web-client',
            created_at__gte=window_start,
            message__icontains=user.email,
        ).exists()
        if recent_alert:
            return

        message = f'{user.email} has {failures} failed FaceGuard access attempts in the last 15 minutes.'
        Alert.objects.create(
            alert_type=Alert.AlertType.MULTIPLE_FAIL,
            message=message,
            camera_id=camera_id or 'web-client',
        )

        try:
            from zones.tasks import _send_email_alert, _send_sms_alert
            _send_email_alert(camera_id or 'web-client', 'repeated_failed_attempts', 0.0, user.get_full_name() or user.email)
            _send_sms_alert(camera_id or 'web-client', 'repeated_failed_attempts', user.get_full_name() or user.email)
        except Exception as notify_exc:
            logger.warning('Repeated-failure notification could not be sent: %s', notify_exc)
    except Exception as exc:
        logger.warning('Failed to create repeated-failure alert: %s', exc)


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
    permission_classes = [permissions.IsAdminUser]

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

        user = None
        email = data.get('email', '').strip()
        if email:
            from users.models import User
            first_name, last_name = _split_name(data['name'])
            user, user_created = User.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'role': data.get('role', 'viewer'),
                },
            )
            if user_created:
                user.set_password(data['password'])
            else:
                user.first_name = first_name
                user.last_name = last_name
                user.role = data.get('role', user.role)
                if data.get('password'):
                    user.set_password(data['password'])
            user.save()

        lookup = {'user': user} if user else {'employee_id': data.get('employee_id') or None}
        person, created = EnrolledPerson.objects.get_or_create(
            **lookup,
            defaults={
                'name':        data['name'],
                'department':  data.get('department', ''),
                'enrolled_by': request.user,
                'notes':       data.get('notes', ''),
            },
        )
        if not created:
            person.name       = data['name']
            person.department = data.get('department', person.department)
            person.notes      = data.get('notes', person.notes)
            if user:
                person.user = user
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
            'user_id':          user.id if user else None,
            'name':             person.name,
            'email':            user.email if user else '',
            'embeddings_saved': embeddings_saved,
            'errors':           errors,
            'created':          created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class SelfEnrolView(APIView):
    """
    POST /api/self-enrol/
    Body (multipart): name, email, password, password2, department, images[] (1-5 files)
    Public self-service enrollment for first-time users.
    """
    parser_classes     = [MultiPartParser, FormParser]
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SelfEnrolmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {'success': False, 'message': 'Registration failed.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        images = request.FILES.getlist('images')
        if not images:
            return Response(
                {
                    'success': False,
                    'message': 'At least one face image is required.',
                    'errors': {'images': ['This field is required.']},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_images = settings.FACE_RECOGNITION['MAX_ENROL_IMAGES']
        if len(images) > max_images:
            return Response(
                {'success': False, 'message': f'Maximum {max_images} face images are allowed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        first_name, last_name = _split_name(data['name'])
        errors = []

        try:
            with transaction.atomic():
                from users.models import User
                user = User.objects.create_user(
                    email=data['email'],
                    password=data['password'],
                    first_name=first_name,
                    last_name=last_name,
                    role=User.Role.VIEWER,
                )
                person = EnrolledPerson.objects.create(
                    user=user,
                    name=data['name'],
                    department=data.get('department', ''),
                    enrolled_by=None,
                    notes='Self-service enrollment',
                )

                embeddings_saved = 0
                for img_file in images:
                    suffix = os.path.splitext(img_file.name)[1] or '.jpg'
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        for chunk in img_file.chunks():
                            tmp.write(chunk)
                        tmp_path = tmp.name

                    try:
                        vector = extract_embedding(tmp_path)
                        emb = FaceEmbedding(person=person, model_name=settings.FACE_RECOGNITION['MODEL'])
                        emb.set_vector(vector)
                        emb.image.save(img_file.name, img_file, save=False)
                        emb.save()
                        embeddings_saved += 1
                    except (ValueError, RuntimeError) as exc:
                        errors.append({'file': img_file.name, 'error': str(exc)})
                    finally:
                        os.unlink(tmp_path)

                if embeddings_saved == 0:
                    raise ValueError('No valid faces found in the captured images.')
        except ValueError as exc:
            logger.warning('Self-enrollment failed for %s: %s', data.get('email'), exc)
            return Response(
                {
                    'success': False,
                    'message': str(exc),
                    'errors': {'images': errors or [str(exc)]},
                },
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                'success': True,
                'message': 'Registration successful. Redirecting to dashboard.',
                'person_id': person.id,
                'embeddings_saved': embeddings_saved,
                'errors': errors,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data,
                'redirect_url': '/dashboard/',
            },
            status=status.HTTP_201_CREATED,
        )


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
    permission_classes = [permissions.IsAuthenticated]

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
            _record_zone_event(
                user=request.user,
                person=None,
                outcome='denied',
                camera_id=camera_id,
                liveness_pass=False,
                reason='liveness_failed',
            )
            _flag_repeated_failures(request.user, camera_id)
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
            _record_zone_event(
                user=request.user,
                person=None,
                outcome='error',
                camera_id=camera_id,
                liveness_pass=True,
                reason=str(e),
            )
            return Response({'outcome': 'error', 'detail': str(e)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        # 4. Match against the enrolled face for this login user.
        own_profile = getattr(request.user, 'face_profile', None)
        if own_profile:
            allowed_embeddings = FaceEmbedding.objects.filter(person=own_profile, person__is_active=True)
        elif request.user.role in ('admin', 'guard'):
            allowed_embeddings = FaceEmbedding.objects.filter(person__is_active=True)
        else:
            VerificationLog.objects.create(
                outcome      = VerificationLog.Outcome.DENIED,
                liveness_pass= True,
                camera_id    = camera_id,
                requested_by = request.user,
                error_detail = 'No enrolled face image for this user',
            )
            _record_zone_event(
                user=request.user,
                person=None,
                outcome='denied',
                camera_id=camera_id,
                liveness_pass=True,
                reason='face_not_enrolled',
            )
            return Response({
                'outcome': 'denied',
                'reason': 'face_not_enrolled',
                'detail': 'No face image has been enrolled for this user.',
                'liveness': {'passed': True, **liveness.__dict__},
            }, status=status.HTTP_200_OK)

        person, confidence, distance = find_best_match(probe_vector, embeddings=allowed_embeddings)
        wrong_user = bool(own_profile and person and person.id != own_profile.id)

        outcome = (
            VerificationLog.Outcome.GRANTED
            if person and confidence >= cfg['CONFIDENCE_THRESHOLD'] and not wrong_user
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
            error_detail   = 'Face belongs to another user' if wrong_user else '',
        )
        _record_zone_event(
            user=request.user,
            person=person if outcome == VerificationLog.Outcome.GRANTED else None,
            outcome=outcome,
            confidence=confidence,
            camera_id=camera_id,
            liveness_pass=True,
            reason='wrong_user' if wrong_user else ('face_not_recognised' if outcome == VerificationLog.Outcome.DENIED else ''),
        )
        if outcome == VerificationLog.Outcome.DENIED:
            _flag_repeated_failures(request.user, camera_id)

        response_data = {
            'outcome':    outcome,
            'confidence': round(confidence, 4),
            'distance':   round(distance, 4),
            'liveness':   {'passed': True, **liveness.__dict__},
            'redirect_url': '/dashboard/' if outcome == VerificationLog.Outcome.GRANTED else '',
        }
        if wrong_user:
            response_data['reason'] = 'wrong_user'
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
