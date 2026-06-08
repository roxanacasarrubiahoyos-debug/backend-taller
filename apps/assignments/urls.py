from django.urls import path
from apps.assignments import views_app

app_name = 'assignments'

# App móvil - /api/app/assignments/
app_patterns = [
    path('<int:pk>/', views_app.assignment_detail, name='app-detail'),
    path('incident/<int:incident_id>/active/', views_app.active_assignment, name='app-active'),
]
