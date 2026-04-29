"""
Views for violations: warnings, violations, rule config APIs.
"""
import csv
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Warning, Violation, RuleConfig
from .serializers import WarningSerializer, ViolationSerializer, RuleConfigSerializer


class WarningViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only access to warnings."""
    serializer_class = WarningSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        org = self.request.organization
        if not org:
            return Warning.objects.none()
        qs = Warning.objects.filter(organization=org).select_related('user')

        date = self.request.query_params.get('date')
        user_id = self.request.query_params.get('user_id')
        if date:
            qs = qs.filter(created_at__date=date)
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs

    @action(detail=False, methods=['get'], url_path='today')
    def today(self, request):
        today = timezone.now().date()
        qs = self.get_queryset().filter(created_at__date=today)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class ViolationViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only access to violations."""
    serializer_class = ViolationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        org = self.request.organization
        if not org:
            return Violation.objects.none()
        qs = Violation.objects.filter(organization=org).select_related('user')

        date = self.request.query_params.get('date')
        user_id = self.request.query_params.get('user_id')
        if date:
            qs = qs.filter(date=date)
        if user_id:
            qs = qs.filter(user_id=user_id)
        return qs

    @action(detail=False, methods=['get'], url_path='export-csv')
    def export_csv(self, request):
        qs = self.get_queryset()
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="violations.csv"'

        writer = csv.writer(response)
        writer.writerow(['Student Name', 'Date', 'Warning Count', 'Expelled'])

        for v in qs:
            writer.writerow([
                v.user.get_full_name(), v.date, v.warning_count, v.is_expelled
            ])
        return response


class RuleConfigViewSet(viewsets.ViewSet):
    """Get/update organization rule configuration."""
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        org = request.organization
        if not org:
            return Response({'error': 'No organization'}, status=400)
        config, _ = RuleConfig.objects.get_or_create(organization=org)
        serializer = RuleConfigSerializer(config)
        return Response(serializer.data)

    def create(self, request):
        org = request.organization
        if not org:
            return Response({'error': 'No organization'}, status=400)
        config, _ = RuleConfig.objects.get_or_create(organization=org)
        serializer = RuleConfigSerializer(config, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)
