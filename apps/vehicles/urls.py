from django.urls import path
from apps.vehicles import views

app_name = 'vehicles'

# App móvil - /api/app/vehicles/
app_patterns = [
    path('', views.VehicleViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='app-list'),
    path('<int:pk>/', views.VehicleViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='app-detail'),
]
