from django.contrib import admin
from .models import Workshop, Technician, WorkshopRating


@admin.register(Workshop)
class WorkshopAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'is_active', 'is_verified', 'rating_avg', 'total_services']
    list_filter = ['is_active', 'is_verified', 'created_at']
    search_fields = ['name', 'owner__user__username', 'phone', 'email']
    raw_id_fields = ['owner']


@admin.register(Technician)
class TechnicianAdmin(admin.ModelAdmin):
    list_display = ['name', 'workshop', 'phone', 'is_available', 'user']
    list_filter = ['is_available', 'workshop']
    search_fields = ['name', 'phone', 'workshop__name', 'user__username']
    raw_id_fields = ['workshop', 'user']


@admin.register(WorkshopRating)
class WorkshopRatingAdmin(admin.ModelAdmin):
    list_display = ['workshop', 'client', 'score', 'created_at']
    list_filter = ['score', 'created_at']
    search_fields = ['workshop__name', 'client__user__username']
    raw_id_fields = ['workshop', 'client']
