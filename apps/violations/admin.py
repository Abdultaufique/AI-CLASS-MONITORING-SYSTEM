"""
Admin registration for violations models.
"""
from django.contrib import admin
from .models import Warning, Violation, RuleConfig


@admin.register(Warning)
class WarningAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization', 'level', 'reason', 'camera_location', 'created_at']
    list_filter = ['level', 'organization', 'created_at']
    search_fields = ['user__first_name', 'user__last_name']


@admin.register(Violation)
class ViolationAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization', 'date', 'warning_count', 'is_expelled']
    list_filter = ['organization', 'date', 'is_expelled']
    search_fields = ['user__first_name', 'user__last_name']
    date_hierarchy = 'date'


@admin.register(RuleConfig)
class RuleConfigAdmin(admin.ModelAdmin):
    list_display = ['organization', 'max_warnings_per_day', 'max_violations_before_expel', 'cooldown_seconds']
