from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, ClientProfile, WorkshopOwnerProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'role', 'is_verified', 'is_active']
    list_filter = ['role', 'is_verified', 'is_active', 'is_staff']
    search_fields = ['username', 'email', 'first_name', 'last_name']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('Información Adicional', {
            'fields': ('role', 'phone', 'avatar', 'fcm_token', 'is_verified')
        }),
    )

    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Información Adicional', {
            'fields': ('role', 'phone', 'is_verified')
        }),
    )


@admin.register(ClientProfile)
class ClientProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'emergency_contact_name', 'stripe_customer_id']
    search_fields = ['user__username', 'user__email', 'emergency_contact_name']
    raw_id_fields = ['user']


@admin.register(WorkshopOwnerProfile)
class WorkshopOwnerProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'national_id', 'stripe_account_id']
    search_fields = ['user__username', 'user__email', 'national_id']
    raw_id_fields = ['user']
