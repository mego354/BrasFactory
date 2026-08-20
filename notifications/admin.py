from django.contrib import admin
from .models import TelegramProfile, MagicLoginToken


@admin.register(TelegramProfile)
class TelegramProfileAdmin(admin.ModelAdmin):
    list_display = ['chat_id', 'first_name', 'username', 'phone', 'entity_type', 'entity_id', 'is_authenticated', 'updated_at']
    list_filter = ['entity_type', 'is_authenticated']
    search_fields = ['chat_id', 'first_name', 'username', 'phone']
    readonly_fields = ['chat_id', 'created_at', 'updated_at']
    ordering = ['-updated_at']


@admin.register(MagicLoginToken)
class MagicLoginTokenAdmin(admin.ModelAdmin):
    list_display = ['name', 'entity_type', 'entity_id', 'is_used', 'expires_at', 'created_at']
    list_filter = ['entity_type', 'is_used']
    search_fields = ['name', 'token']
    readonly_fields = ['token', 'entity_type', 'entity_id', 'name', 'expires_at', 'is_used', 'created_at']
    ordering = ['-created_at']

    def has_add_permission(self, request):
        return False
