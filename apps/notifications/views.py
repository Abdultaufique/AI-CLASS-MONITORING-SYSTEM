"""
Views for notifications.
"""
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification
from .serializers import NotificationSerializer
from .services.notification_service import NotificationService


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        org = self.request.organization
        if not org:
            return Notification.objects.none()
        return Notification.objects.filter(organization=org)

    @action(detail=False, methods=['get'], url_path='unread')
    def unread(self, request):
        org = request.organization
        if not org:
            return Response([])
        notifications = NotificationService.get_unread(org)
        serializer = self.get_serializer(notifications, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        NotificationService.mark_read(pk)
        return Response({'status': 'ok'})

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        org = request.organization
        if org:
            NotificationService.mark_all_read(org)
        return Response({'status': 'ok'})
