from django.contrib import admin
from .models import OTPRecord


@admin.register(OTPRecord)
class OTPRecordAdmin(admin.ModelAdmin):
    list_display = ['phone', 'entity_type', 'entity_id', 'is_used', 'attempt_count', 'expires_at', 'created_at']
    list_filter = ['entity_type', 'is_used']
    search_fields = ['phone']
    readonly_fields = ['phone', 'otp_hash', 'entity_type', 'entity_id', 'expires_at', 'attempt_count', 'created_at']
    ordering = ['-created_at']

    def has_add_permission(self, request):
        return False
