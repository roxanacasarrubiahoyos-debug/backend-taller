from django.urls import path

from apps.assignments import views_technician
from apps.ai_engine import voice_report_views

app_name = 'technician'

technician_app_patterns = [
    path('assignments/', views_technician.list_assignments, name='assignments-list'),
    path('assignments/<int:pk>/', views_technician.assignment_detail, name='assignments-detail'),
    path('assignments/<int:pk>/status/', views_technician.update_assignment_status, name='assignments-status'),
    path('reports/voice-query/', voice_report_views.technician_voice_query, name='reports-voice-query'),
]
