"""
URL routing for violations app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'violations'

router = DefaultRouter()
router.register(r'warnings', views.WarningViewSet, basename='warning')
router.register(r'violations', views.ViolationViewSet, basename='violation')
router.register(r'rules', views.RuleConfigViewSet, basename='rule-config')

urlpatterns = [
    path('', include(router.urls)),
]
