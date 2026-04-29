"""
Admin registration for accounts models.
"""
from django.contrib import admin
from .models import Organization, UserProfile


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'is_active', 'max_cameras', 'max_students', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'organization', 'role', 'student_id', 'is_active', 'created_at']
    list_filter = ['role', 'organization', 'is_active']
    search_fields = ['user__first_name', 'user__last_name', 'student_id']
    raw_id_fields = ['user']
