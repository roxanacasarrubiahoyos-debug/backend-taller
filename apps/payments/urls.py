from django.urls import path
from apps.payments import views_app, views_web, views_admin, views_subscription_web
from apps.payments.views_subscription_admin import WorkshopSubscriptionPlanViewSet

app_name = 'payments'

# App móvil - /api/app/payments/
app_patterns = [
    path('create-intent/', views_app.create_payment_intent, name='app-create-intent'),
    path('confirm/', views_app.confirm_payment, name='app-confirm'),
    path('history/', views_app.payment_history, name='app-history'),
    path('<int:pk>/', views_app.payment_detail, name='app-detail'),
]

shared_patterns = [
    path('stripe/webhook/', views_app.stripe_webhook, name='stripe-webhook'),
]

# Web - /api/web/payments/
web_patterns = [
    path('earnings/', views_web.earnings_summary, name='web-earnings'),
    path('', views_web.payment_list, name='web-list'),
    path('subscription-plans/', views_subscription_web.public_subscription_plans, name='web-sub-plans'),
    path('subscriptions/me/', views_subscription_web.my_subscription, name='web-sub-me'),
    path('subscriptions/checkout/', views_subscription_web.create_subscription_checkout, name='web-sub-checkout'),
    path('subscriptions/verify/', views_subscription_web.verify_subscription_session, name='web-sub-verify'),
]

# Admin - /api/admin-api/
admin_patterns = [
    # Comisiones
    path('commission/', views_admin.CommissionConfigViewSet.as_view({
        'get': 'list',
        'post': 'create'
    }), name='admin-commission-list'),
    path('commission/<int:pk>/', views_admin.CommissionConfigViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    }), name='admin-commission-detail'),
    path('commission/current/', views_admin.CommissionConfigViewSet.as_view({
        'get': 'current'
    }), name='admin-commission-current'),

    # Pagos
    path('payments/', views_admin.PaymentAdminViewSet.as_view({
        'get': 'list'
    }), name='admin-payments-list'),
    path('payments/<int:pk>/', views_admin.PaymentAdminViewSet.as_view({
        'get': 'retrieve'
    }), name='admin-payments-detail'),

    # Métricas
    path('metrics/', views_admin.platform_metrics, name='admin-metrics'),

    # Planes de suscripción talleres
    path('subscription-plans/', WorkshopSubscriptionPlanViewSet.as_view({
        'get': 'list',
        'post': 'create',
    }), name='admin-sub-plans-list'),
    path('subscription-plans/<int:pk>/', WorkshopSubscriptionPlanViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy',
    }), name='admin-sub-plans-detail'),
]
