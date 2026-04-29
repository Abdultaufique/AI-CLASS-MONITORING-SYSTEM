"""
Models for multi-tenant accounts: Organization, UserProfile.
"""
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Organization(models.Model):
    """Represents a school, college, or library — the tenant unit."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    address = models.TextField(blank=True)
    logo = models.ImageField(upload_to='org_logos/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    max_cameras = models.IntegerField(default=5)
    max_students = models.IntegerField(default=200)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """Extended user profile linked to an organization with role & face data."""
    ROLE_CHOICES = [
        ('admin', 'Administrator'),
        ('moderator', 'Moderator'),
        ('viewer', 'Viewer'),
        ('student', 'Student'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='members'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    student_id = models.CharField(max_length=50, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    face_image = models.ImageField(upload_to='faces/', blank=True, null=True)
    face_encoding = models.BinaryField(blank=True, null=True,
                                        help_text='Serialized face encoding numpy array')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user__first_name', 'user__last_name']

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.organization.name})"

    @property
    def full_name(self):
        return self.user.get_full_name() or self.user.username

    @property
    def today_warnings_count(self):
        """Count of warnings issued today."""
        today = timezone.now().date()
        return self.user.warnings.filter(
            created_at__date=today
        ).count()
