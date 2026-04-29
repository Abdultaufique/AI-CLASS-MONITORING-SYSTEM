"""
Serializers for the monitoring app.
"""
from rest_framework import serializers
from .models import Camera, Attendance


class CameraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Camera
        fields = ['id', 'name', 'location', 'source_type', 'source_url',
                  'is_active', 'is_monitoring', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class AttendanceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='user.get_full_name', read_only=True)
    camera_name = serializers.CharField(source='camera.name', read_only=True, default='—')

    class Meta:
        model = Attendance
        fields = ['id', 'user', 'student_name', 'camera', 'camera_name',
                  'timestamp', 'face_confidence', 'date']
        read_only_fields = ['id', 'timestamp', 'date']
