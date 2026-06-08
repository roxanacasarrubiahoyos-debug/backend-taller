from django.urls import path
from apps.notifications import views_app, views_web, views_web_push
from apps.notifications.sse_views import notifications_stream, incident_stream

app_name = 'notifications'

# App móvil - /api/app/notifications/
app_patterns = [
    path('', views_app.notification_list, name='app-list'),
    path('<int:pk>/read/', views_app.mark_as_read, name='app-mark-read'),
    path('read-all/', views_app.mark_all_as_read, name='app-mark-all-read'),
    path('unread-count/', views_app.unread_count, name='app-unread-count'),
    path('stream/', notifications_stream, name='app-stream'),
    path('incidents/<int:incident_id>/stream/', incident_stream, name='app-incident-stream'),
]

# Web - /api/web/notifications/
web_patterns = [
    path('', views_web.notification_list, name='web-list'),
    path('unread-count/', views_web.unread_count_web, name='web-unread-count'),
    path('<int:pk>/read/', views_web.mark_as_read, name='web-mark-read'),
    path('read-all/', views_web.mark_all_as_read, name='web-mark-all-read'),
    path('stream/', notifications_stream, name='web-stream'),
    path('web-push/vapid-public-key/', views_web_push.vapid_public_key_view, name='web-push-vapid'),
    path('web-push/subscribe/', views_web_push.subscribe, name='web-push-subscribe'),
    path('web-push/unsubscribe/', views_web_push.unsubscribe, name='web-push-unsubscribe'),
]
