"""
URL routing for dashboard app.
"""
from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.index, name='index'),
    path('attendance/', views.attendance_view, name='attendance'),
    path('violations/', views.violations_view, name='violations'),
    path('students/', views.students_view, name='students'),
    path('cameras/', views.cameras_view, name='cameras'),
    path('settings/', views.settings_view, name='settings'),
    path('live-demo/', views.live_demo_view, name='live_demo'),
    path('live-demo/feed/', views.live_demo_feed, name='live_demo_feed'),
    path('live-demo/start/', views.live_demo_start, name='live_demo_start'),
    path('live-demo/stop/', views.live_demo_stop, name='live_demo_stop'),
    path('api/stats/', views.dashboard_stats_api, name='stats-api'),
]
