import os
import tempfile

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import ReadOnlyPasswordHashField
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from recognition.matching import extract_embedding
from recognition.models import EnrolledPerson, FaceEmbedding
from .models import User


class FaceEnrollmentMixin:
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

    def clean_face_image(self):
        image = self.cleaned_data.get('face_image')
        if image:
            self._face_vector = self._extract_face_vector(image)
            image.seek(0)
        return image

    def save_face_profile(self, user, enrolled_by=None):
        image = self.cleaned_data.get('face_image')
        if not image:
            return

        full_name = user.get_full_name() or user.username or user.email
        person, _ = EnrolledPerson.objects.get_or_create(
            user=user,
            defaults={
                'name': full_name,
                'employee_id': self.cleaned_data.get('employee_id') or None,
                'department': self.cleaned_data.get('department', ''),
                'notes': self.cleaned_data.get('notes', ''),
                'enrolled_by': enrolled_by if getattr(enrolled_by, 'is_authenticated', False) else None,
            },
        )
        person.name = full_name
        person.employee_id = self.cleaned_data.get('employee_id') or person.employee_id
        person.department = self.cleaned_data.get('department', person.department)
        person.notes = self.cleaned_data.get('notes', person.notes)
        if enrolled_by and not person.enrolled_by_id:
            person.enrolled_by = enrolled_by
        person.save()

        embedding = FaceEmbedding(person=person)
        embedding.set_vector(self._face_vector)
        embedding.image.save(image.name, image, save=False)
        embedding.save()


class UserCreationAdminForm(FaceEnrollmentMixin, forms.ModelForm):
    password1 = forms.CharField(label='Password', widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirm password', widget=forms.PasswordInput)
    face_image = forms.ImageField(required=False, help_text='Photo used for face login verification.')
    employee_id = forms.CharField(required=False)
    department = forms.CharField(required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea)

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'role', 'is_staff', 'is_active')

    def clean(self):
        cleaned = super().clean()
        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if password1 and password2 and password1 != password2:
            raise ValidationError({'password2': 'Passwords do not match.'})
        if password1:
            validate_password(password1, self.instance)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
            self.save_m2m()
        return user


class UserChangeAdminForm(FaceEnrollmentMixin, forms.ModelForm):
    password = ReadOnlyPasswordHashField()
    face_image = forms.ImageField(required=False, help_text='Upload another photo to replace/add a face login reference.')
    employee_id = forms.CharField(required=False)
    department = forms.CharField(required=False)
    notes = forms.CharField(required=False, widget=forms.Textarea)

    class Meta:
        model = User
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = getattr(self.instance, 'face_profile', None)
        if profile:
            self.fields['employee_id'].initial = profile.employee_id
            self.fields['department'].initial = profile.department
            self.fields['notes'].initial = profile.notes


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = UserCreationAdminForm
    form = UserChangeAdminForm
    model = User
    list_display = ('email', 'username', 'first_name', 'last_name', 'role', 'is_staff', 'is_active', 'last_login')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('email', 'username', 'first_name', 'last_name')
    ordering = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'role')}),
        ('Face login', {'fields': ('face_image', 'employee_id', 'department', 'notes')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 'username', 'first_name', 'last_name', 'role',
                'password1', 'password2', 'face_image', 'employee_id',
                'department', 'notes', 'is_staff', 'is_active',
            ),
        }),
    )
    readonly_fields = ('last_login', 'date_joined')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if hasattr(form, 'save_face_profile') and form.cleaned_data.get('face_image'):
            form.save_face_profile(obj, enrolled_by=request.user)
            self.message_user(request, 'Face login image enrolled for this user.', messages.SUCCESS)
