"""
Admin registration for notifications.
"""
from django.contrib import admin
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['title', 'organization', 'severity', 'notification_type', 'is_read', 'created_at']
    list_filter = ['severity', 'notification_type', 'is_read', 'organization']
    search_fields = ['title', 'message']
