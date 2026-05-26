"""
Custom User model for FaceGuard.
Roles: Admin | Guard | Viewer
"""

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', User.Role.ADMIN)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):

    class Role(models.TextChoices):
        ADMIN  = 'admin',  'Admin'
        GUARD  = 'guard',  'Guard'
        VIEWER = 'viewer', 'Viewer'

    # Core fields
    email      = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150)
    last_name  = models.CharField(max_length=150)
    role       = models.CharField(max_length=10, choices=Role.choices, default=Role.VIEWER)

    # Status
    is_active  = models.BooleanField(default=True)
    is_staff   = models.BooleanField(default=False)

    # Timestamps
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login  = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD  = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    class Meta:
        db_table = 'fg_users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        return f'{self.get_full_name()} <{self.email}> [{self.role}]'

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip()

    # ------------------------------------------------------------------ #
    #  Role helper properties
    # ------------------------------------------------------------------ #
    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_guard(self):
        return self.role == self.Role.GUARD

    @property
    def is_viewer(self):
        return self.role == self.Role.VIEWER