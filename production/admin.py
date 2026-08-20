from django.contrib import admin
from django.utils import timezone
from .models import ProductionEntry


@admin.register(ProductionEntry)
class ProductionEntryAdmin(admin.ModelAdmin):
    list_display = [
        'production_date', 'variant', 'stage', 'worker',
        'quantity', 'unit_price_snapshot', 'total_amount',
        'entered_by_worker', 'is_cancelled', 'created_by', 'created_at'
    ]
    list_filter = ['entered_by_worker', 'is_cancelled', 'stage', 'production_date', 'worker']
    search_fields = [
        'variant__sku', 'variant__product_model__code',
        'worker__name', 'stage__name'
    ]
    readonly_fields = [
        'variant', 'stage', 'worker', 'quantity',
        'unit_price_snapshot', 'total_amount',
        'entered_by_worker', 'created_by', 'created_at',
        'is_cancelled', 'cancelled_by', 'cancelled_at'
    ]
    date_hierarchy = 'production_date'
    ordering = ['-production_date', '-created_at']

    fieldsets = [
        ('بيانات الإنتاج', {
            'fields': ['variant', 'stage', 'worker', 'quantity',
                       'unit_price_snapshot', 'total_amount', 'production_date', 'notes']
        }),
        ('المراجعة والتدقيق', {
            'fields': ['entered_by_worker', 'created_by', 'created_at'],
        }),
        ('الإلغاء', {
            'fields': ['is_cancelled', 'cancellation_reason', 'cancelled_by', 'cancelled_at'],
            'classes': ['collapse'],
        }),
    ]

    def has_delete_permission(self, request, obj=None):
        """Only superusers can delete. Prefer cancellation."""
        return request.user.is_superuser

    def has_add_permission(self, request):
        """Production entries should be created through the application, not admin."""
        return request.user.is_superuser

    def cancel_entries(self, request, queryset):
        count = 0
        for entry in queryset.filter(is_cancelled=False):
            entry.is_cancelled = True
            entry.cancellation_reason = 'إلغاء جماعي من لوحة الإدارة'
            entry.cancelled_by = request.user
            entry.cancelled_at = timezone.now()
            entry.save()
            count += 1
        self.message_user(request, f'تم إلغاء {count} سجل.')
    cancel_entries.short_description = 'إلغاء السجلات المختارة'

    actions = ['cancel_entries']
