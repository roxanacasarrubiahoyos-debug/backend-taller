from django.urls import path
from apps.workshops import views_app, views_web, views_admin
from apps.ai_engine import voice_report_views
from apps.payments import reports_views as payment_reports

app_name = 'workshops'

# App móvil - /api/app/workshops/
app_patterns = [
    path('nearby/', views_app.nearby_workshops, name='app-nearby'),
    path('<int:pk>/', views_app.workshop_detail, name='app-detail'),
    path('<int:pk>/rate/', views_app.rate_workshop, name='app-rate'),
]

# Web - /api/web/workshop/
web_patterns = [
    path('', views_web.workshop_detail, name='web-detail'),
    path('create/', views_web.workshop_create, name='web-create'),
    path('dashboard/', views_web.workshop_dashboard, name='web-dashboard'),
    path('earnings/', views_web.workshop_earnings, name='web-earnings'),
    path('reports/voice-query/', voice_report_views.workshop_voice_query, name='web-reports-voice-query'),
    path('reports/export/', payment_reports.workshop_reports_export_xlsx, name='web-reports-export'),

    # Stripe Connect
    path('stripe/connect/create/', views_web.create_stripe_connect_account, name='web-stripe-create'),
    path('stripe/connect/onboarding/', views_web.create_stripe_onboarding_link, name='web-stripe-onboarding'),
    path('stripe/connect/status/', views_web.stripe_connect_status, name='web-stripe-status'),

    # Técnicos
    path('technicians/', views_web.TechnicianViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='web-technicians-list'),
    path('technicians/<int:pk>/', views_web.TechnicianViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='web-technicians-detail'),
    path('technicians/<int:pk>/availability/', views_web.TechnicianViewSet.as_view({
        'patch': 'availability'
    }), name='web-technicians-availability'),
    path('technicians/<int:pk>/location/', views_web.TechnicianViewSet.as_view({
        'patch': 'location'
    }), name='web-technicians-location'),
    path('technicians/<int:pk>/app-access/', views_web.TechnicianViewSet.as_view({
        'post': 'app_access'
    }), name='web-technicians-app-access'),
]

# Admin - /api/admin-api/workshops/
admin_patterns = [
    path('', views_admin.WorkshopAdminViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='admin-list'),
    path('<int:pk>/', views_admin.WorkshopAdminViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='admin-detail'),
    path('<int:pk>/verify/', views_admin.WorkshopAdminViewSet.as_view({
        'patch': 'verify'
    }), name='admin-verify'),
    path('<int:pk>/toggle-active/', views_admin.WorkshopAdminViewSet.as_view({
        'patch': 'toggle_active'
    }), name='admin-toggle-active'),
]
