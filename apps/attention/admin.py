from django.contrib import admin
from .models import AttentionSession, AttentionSnapshot


@admin.register(AttentionSession)
class AttentionSessionAdmin(admin.ModelAdmin):
    list_display  = ('id', 'organization', 'camera', 'started_at', 'status',
                     'aggregate_only', 'alert_threshold')
    list_filter   = ('status', 'aggregate_only', 'organization')
    readonly_fields = ('id', 'started_at', 'ended_at')


@admin.register(AttentionSnapshot)
class AttentionSnapshotAdmin(admin.ModelAdmin):
    list_display  = ('session', 'timestamp', 'class_attention_pct',
                     'total_faces', 'attentive_count', 'alert_active')
    list_filter   = ('alert_active', 'session')
    readonly_fields = ('id', 'timestamp')
