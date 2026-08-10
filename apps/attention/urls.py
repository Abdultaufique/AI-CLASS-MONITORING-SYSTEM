"""
URL routing for attention monitoring app.
Mounted at: /dashboard/attention/ (configured in config/urls.py)
"""
from django.urls import path
from . import views

app_name = 'attention'

urlpatterns = [
    path('',                             views.attention_dashboard,    name='dashboard'),
    path('consent/',                     views.consent_notice,          name='consent'),
    path('session/start/',               views.start_session,           name='session_start'),
    path('session/end/',                 views.end_session,             name='session_end'),
    path('live/',                        views.live_attention_api,      name='live_api'),
    path('session/<str:session_id>/report/',  views.session_report_json,    name='report_json'),
    path('session/<str:session_id>/export/',  views.export_report_csv,      name='export_csv'),
    path('settings/save/',               views.save_attention_settings, name='settings_save'),
]
