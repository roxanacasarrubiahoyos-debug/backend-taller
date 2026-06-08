from django.contrib import admin
from .models import Assignment


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ['id', 'incident', 'workshop', 'technician', 'status', 'distance_km', 'offered_at']
    list_filter = ['status', 'offered_at', 'accepted_at', 'completed_at']
    search_fields = ['incident__id', 'workshop__name', 'technician__name']
    raw_id_fields = ['incident', 'workshop', 'technician']
    readonly_fields = ['offered_at', 'accepted_at', 'completed_at']
