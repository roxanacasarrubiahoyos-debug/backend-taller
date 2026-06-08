from django.contrib import admin
from .models import Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ['plate', 'brand', 'model', 'year', 'client', 'is_active']
    list_filter = ['vehicle_type', 'is_active', 'year']
    search_fields = ['plate', 'brand', 'model', 'vin', 'client__user__username']
    raw_id_fields = ['client']
