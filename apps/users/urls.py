from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from apps.users import views_app, views_web, views_admin

app_name = 'users'

# App móvil - /api/app/auth/
app_patterns = [
    path('register/', views_app.register, name='app-register'),
    path('login/', views_app.login, name='app-login'),
    path('refresh/', TokenRefreshView.as_view(), name='app-token-refresh'),
    path('logout/', views_app.logout, name='app-logout'),
    path('fcm-token/', views_app.fcm_token, name='app-fcm-token'),
    path('test-push/', views_app.test_push_notification, name='app-test-push'),
    path('profile/', views_app.profile, name='app-profile'),
    path('change-password/', views_app.change_password, name='app-change-password'),
]

# Web - /api/web/auth/
web_patterns = [
    path('register/', views_web.register, name='web-register'),
    path('login/', views_web.login, name='web-login'),
    path('refresh/', TokenRefreshView.as_view(), name='web-token-refresh'),
    path('profile/', views_web.profile, name='web-profile'),
    path('fcm-token/', views_web.update_fcm_token, name='web-fcm-token'),
]

# Admin - /api/admin-api/users/
admin_patterns = [
    path('', views_admin.UserAdminViewSet.as_view({'get': 'list', 'post': 'create'}), name='admin-user-list'),
    path('push-tokens/', views_admin.UserAdminViewSet.as_view({'get': 'push_tokens'}), name='admin-push-tokens'),
    path('test-push-broadcast/', views_admin.UserAdminViewSet.as_view({'post': 'test_push_broadcast'}), name='admin-test-push-broadcast'),
    path('<int:pk>/', views_admin.UserAdminViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='admin-user-detail'),
    path('<int:pk>/toggle-active/', views_admin.UserAdminViewSet.as_view({
        'patch': 'toggle_active'
    }), name='admin-user-toggle-active'),
]
