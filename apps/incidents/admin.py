from django.contrib import admin
from .models import Incident, Evidence, IncidentStatusHistory


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):
    list_display = ['id', 'client', 'status', 'incident_type', 'priority', 'created_at']
    list_filter = ['status', 'incident_type', 'priority', 'created_at']
    search_fields = ['id', 'client__user__username', 'description', 'address_text']
    raw_id_fields = ['client', 'vehicle']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Evidence)
class EvidenceAdmin(admin.ModelAdmin):
    list_display = ['id', 'incident', 'evidence_type', 'transcription_done', 'created_at']
    list_filter = ['evidence_type', 'transcription_done', 'created_at']
    search_fields = ['incident__id', 'label', 'transcription']
    raw_id_fields = ['incident']


@admin.register(IncidentStatusHistory)
class IncidentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ['incident', 'previous_status', 'new_status', 'changed_by', 'changed_at']
    list_filter = ['previous_status', 'new_status', 'changed_at']
    search_fields = ['incident__id', 'notes']
    raw_id_fields = ['incident', 'changed_by']
    readonly_fields = ['changed_at']
