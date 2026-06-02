import os
import tempfile

from django.contrib import admin, messages
from django.core.exceptions import ValidationError

from .matching import extract_embedding
from .models import EnrolledPerson, FaceEmbedding, VerificationLog


class FaceEmbeddingInline(admin.TabularInline):
    model = FaceEmbedding
    extra = 1
    readonly_fields = ('model_name', 'created_at')
    fields = ('image', 'model_name', 'created_at')


@admin.register(EnrolledPerson)
class EnrolledPersonAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'employee_id', 'department', 'is_active', 'embedding_count', 'enrolled_at')
    list_filter = ('is_active', 'department')
    search_fields = ('name', 'employee_id', 'user__email', 'user__username')
    inlines = (FaceEmbeddingInline,)

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in instances:
            if isinstance(obj, FaceEmbedding) and obj.image and not obj.embedding:
                obj.set_vector(self._extract_face_vector(obj.image))
                messages.success(request, f'Face embedding created from {obj.image.name}.')
            obj.save()
        for obj in formset.deleted_objects:
            obj.delete()
        formset.save_m2m()

    def _extract_face_vector(self, image):
        suffix = os.path.splitext(image.name)[1] or '.jpg'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in image.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            return extract_embedding(tmp_path)
        except (ValueError, RuntimeError) as exc:
            raise ValidationError(f'Face image could not be enrolled: {exc}') from exc
        finally:
            os.unlink(tmp_path)


@admin.register(FaceEmbedding)
class FaceEmbeddingAdmin(admin.ModelAdmin):
    list_display = ('person', 'model_name', 'created_at')
    search_fields = ('person__name', 'person__user__email')
    readonly_fields = ('created_at',)
    exclude = ('embedding',)

    def save_model(self, request, obj, form, change):
        if obj.image and not obj.embedding:
            obj.set_vector(self._extract_face_vector(obj.image))
        super().save_model(request, obj, form, change)

    def _extract_face_vector(self, image):
        suffix = os.path.splitext(image.name)[1] or '.jpg'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in image.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
        try:
            return extract_embedding(tmp_path)
        except (ValueError, RuntimeError) as exc:
            raise ValidationError(f'Face image could not be enrolled: {exc}') from exc
        finally:
            os.unlink(tmp_path)


@admin.register(VerificationLog)
class VerificationLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'requested_by', 'matched_person', 'outcome', 'confidence', 'liveness_pass', 'camera_id')
    list_filter = ('outcome', 'liveness_pass', 'created_at')
    search_fields = ('requested_by__email', 'matched_person__name', 'camera_id')
    readonly_fields = ('created_at',)
