from django.contrib import admin
from .models import Worker


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'stages_list', 'is_active', 'created_at']
    list_filter = ['is_active', 'stages']
    search_fields = ['name', 'phone']
    list_editable = ['is_active']
    filter_horizontal = ['stages']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = [
        ('معلومات العامل', {'fields': ['name', 'phone', 'is_active', 'notes']}),
        ('المراحل المسندة', {'fields': ['stages']}),
        ('التواريخ', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def stages_list(self, obj):
        return ', '.join(s.name for s in obj.stages.all())
    stages_list.short_description = 'المراحل'
