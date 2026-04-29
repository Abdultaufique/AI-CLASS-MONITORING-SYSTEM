"""
Admin registration for monitoring models.
"""
from django.contrib import admin
from .models import Camera, Attendance


@admin.register(Camera)
class CameraAdmin(admin.ModelAdmin):
    list_display = ['name', 'organization', 'source_type', 'is_active', 'is_monitoring', 'location']
    list_filter = ['organization', 'source_type', 'is_active', 'is_monitoring']
    search_fields = ['name', 'location']


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization', 'camera', 'date', 'timestamp', 'face_confidence']
    list_filter = ['organization', 'date', 'camera']
    search_fields = ['user__first_name', 'user__last_name']
    date_hierarchy = 'date'
