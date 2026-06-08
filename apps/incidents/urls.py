from django.urls import path
from apps.incidents import views_app, views_web, views_admin

app_name = 'incidents'

# App móvil - /api/app/incidents/
app_patterns = [
    path('', views_app.IncidentViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='app-list'),
    path('<int:pk>/', views_app.IncidentViewSet.as_view({
        'get': 'retrieve'
    }), name='app-detail'),
    path('<int:pk>/upload-evidence/', views_app.IncidentViewSet.as_view({
        'post': 'upload_evidence'
    }), name='app-upload-evidence'),
    path('<int:pk>/evidence/', views_app.IncidentViewSet.as_view({
        'post': 'upload_evidence',
        'get': 'evidences'
    }), name='app-evidence'),
    path('<int:pk>/evidences/', views_app.IncidentViewSet.as_view({
        'get': 'evidences'
    }), name='app-evidences'),
    path('<int:pk>/assignment/', views_app.IncidentViewSet.as_view({
        'get': 'assignment'
    }), name='app-assignment'),
    path('<int:pk>/cancel/', views_app.IncidentViewSet.as_view({
        'post': 'cancel'
    }), name='app-cancel'),
    path('<int:pk>/status-history/', views_app.IncidentViewSet.as_view({
        'get': 'status_history'
    }), name='app-status-history'),
    path('<int:pk>/offered-workshops/', views_app.IncidentViewSet.as_view({
        'get': 'offered_workshops'
    }), name='app-offered-workshops'),
    path('<int:pk>/refresh-workshop-offers/', views_app.refresh_workshop_offers, name='app-refresh-workshop-offers'),
    path('<int:pk>/select-workshop/', views_app.IncidentViewSet.as_view({
        'post': 'select_workshop'
    }), name='app-select-workshop'),
    path('<int:pk>/quotes/', views_app.IncidentViewSet.as_view({
        'get': 'quotes'
    }), name='app-quotes'),
    path('<int:pk>/quotes/respond/', views_app.IncidentViewSet.as_view({
        'post': 'respond_quote'
    }), name='app-quotes-respond'),
]

# Web - /api/web/incidents/
web_patterns = [
    path('available/', views_web.available_incidents, name='web-available'),
    path('<int:pk>/', views_web.incident_detail, name='web-detail'),
    path('<int:pk>/accept/', views_web.accept_incident, name='web-accept'),
    path('<int:pk>/reject/', views_web.reject_incident, name='web-reject'),
    path('<int:pk>/status/', views_web.update_incident_status, name='web-update-status'),
    path('<int:pk>/complete/', views_web.complete_incident, name='web-complete'),
    path('<int:pk>/quote/', views_web.create_service_quote, name='web-quote'),
    path('history/', views_web.incident_history, name='web-history'),
]

# Admin - /api/admin-api/incidents/
admin_patterns = [
    path('', views_admin.IncidentAdminViewSet.as_view({
        'get': 'list'
    }), name='admin-list'),
    path('<int:pk>/', views_admin.IncidentAdminViewSet.as_view({
        'get': 'retrieve'
    }), name='admin-detail'),
]
