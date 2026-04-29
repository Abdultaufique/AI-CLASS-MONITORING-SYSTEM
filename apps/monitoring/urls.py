"""
URL routing for monitoring app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'monitoring'

router = DefaultRouter()
router.register(r'cameras', views.CameraViewSet, basename='camera')
router.register(r'attendance', views.AttendanceViewSet, basename='attendance')

urlpatterns = [
    path('', include(router.urls)),
]
