"""
Serializers for the violations app.
"""
from rest_framework import serializers
from .models import Warning, Violation, RuleConfig


class RuleConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = RuleConfig
        fields = ['max_warnings_per_day', 'max_violations_before_expel',
                  'audio_threshold', 'cooldown_seconds', 'auto_reset_daily']


class WarningSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = Warning
        fields = ['id', 'user', 'student_name', 'level', 'reason',
                  'camera_location', 'created_at']
        read_only_fields = ['id', 'created_at']


class ViolationSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='user.get_full_name', read_only=True)

    class Meta:
        model = Violation
        fields = ['id', 'user', 'student_name', 'date', 'warning_count',
                  'is_expelled', 'created_at']
        read_only_fields = ['id', 'created_at']
