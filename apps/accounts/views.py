"""
Views for accounts: login, logout, user/org management, face upload.
"""
import pickle
import numpy as np
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from .models import Organization, UserProfile
from .serializers import OrganizationSerializer, UserProfileSerializer


# ── Auth Views ──────────────────────────────────────────────

def login_view(request):
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect('dashboard:index')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', '/dashboard/')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')

    return render(request, 'accounts/login.html')


@login_required
def logout_view(request):
    """Log out the user."""
    logout(request)
    return redirect('accounts:login')


@login_required
def profile_view(request):
    """User profile page."""
    return render(request, 'accounts/profile.html')


# ── API ViewSets ──────────────────────────────────────────────

class OrganizationViewSet(viewsets.ModelViewSet):
    """CRUD for organizations (superadmin only)."""
    serializer_class = OrganizationSerializer
    permission_classes = [permissions.IsAdminUser]
    queryset = Organization.objects.all()


class UserProfileViewSet(viewsets.ModelViewSet):
    """CRUD for user profiles, scoped to the requesting user's organization."""
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        org = self.request.organization
        if org:
            qs = UserProfile.objects.filter(organization=org)
        else:
            qs = UserProfile.objects.none()

        role = self.request.query_params.get('role')
        if role:
            qs = qs.filter(role=role)
        return qs.select_related('user', 'organization')

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)

    @action(detail=True, methods=['post'], url_path='upload-face')
    def upload_face(self, request, pk=None):
        """Upload a face image and generate encoding."""
        profile = self.get_object()
        face_image = request.FILES.get('face_image')

        if not face_image:
            return Response(
                {'error': 'No face image provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        profile.face_image = face_image
        profile.save()

        # Try to generate face encoding
        try:
            from ai_engine.face_detector import FaceDetector
            detector = FaceDetector()
            encoding = detector.encode_face_from_image(profile.face_image.path)

            if encoding is not None:
                profile.face_encoding = pickle.dumps(encoding)
                profile.save()
                return Response({'status': 'Face image uploaded and encoded successfully'})
            else:
                return Response({
                    'status': 'Face image uploaded but no face detected. Please upload a clearer photo.'
                }, status=status.HTTP_400_BAD_REQUEST)
        except ImportError:
            profile.save()
            return Response({
                'status': 'Face image uploaded. Encoding will be generated when AI engine is available.'
            })

    @action(detail=True, methods=['post'], url_path='upload-multiple-faces')
    def upload_multiple_faces(self, request, pk=None):
        """Upload multiple face images and generate combined encodings."""
        profile = self.get_object()
        images = request.FILES.getlist('face_images')

        if not images:
            return Response(
                {'error': 'No images provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        from apps.monitoring.services.face_service import FaceService
        face_svc = FaceService()

        # Load existing encodings if any
        existing_encodings = []
        if profile.face_encoding:
            try:
                data = pickle.loads(profile.face_encoding)
                existing_encodings = data if isinstance(data, list) else [data]
            except Exception:
                existing_encodings = []

        # Save images and generate encodings
        import os
        from django.conf import settings
        save_dir = os.path.join(settings.MEDIA_ROOT, 'faces', str(profile.id))
        os.makedirs(save_dir, exist_ok=True)

        new_encodings = []
        saved_count = 0
        for img_file in images:
            ext = os.path.splitext(img_file.name)[1].lower()
            if ext not in ('.jpg', '.jpeg', '.png'):
                continue
            filepath = os.path.join(save_dir, f"face_{saved_count}{ext}")
            with open(filepath, 'wb') as f:
                for chunk in img_file.chunks():
                    f.write(chunk)

            enc = face_svc.encode_face_from_image(filepath)
            if enc is not None:
                new_encodings.append(enc)
                saved_count += 1

            # Save first image as profile picture
            if saved_count == 1 and not profile.face_image:
                profile.face_image = f'faces/{profile.id}/face_0{ext}'

        if new_encodings:
            all_encodings = existing_encodings + [e.tolist() if hasattr(e, 'tolist') else e for e in new_encodings]
            profile.face_encoding = pickle.dumps(all_encodings)
            profile.save()
            return Response({
                'status': f'Added {len(new_encodings)} encoding(s) from {saved_count} image(s)',
                'total_encodings': len(all_encodings),
            })
        else:
            return Response(
                {'error': 'No faces detected in uploaded images. Use clear, well-lit photos.'},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=False, methods=['get'], url_path='students')
    def list_students(self, request):
        """List only students in the organization."""
        qs = self.get_queryset().filter(role='student')
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
