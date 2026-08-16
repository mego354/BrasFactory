"""
Catalog Admin — Professional admin interface for all catalog models.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import Color, Size, Client, ProductionStage, ProductModel, ProductModelStage, ProductVariant


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']
    list_editable = ['is_active']
    ordering = ['name']


@admin.register(Size)
class SizeAdmin(admin.ModelAdmin):
    list_display = ['name', 'sort_order', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']
    list_editable = ['sort_order', 'is_active']
    ordering = ['sort_order']


@admin.register(ProductionStage)
class ProductionStageAdmin(admin.ModelAdmin):
    list_display = ['name', 'sort_order', 'is_active', 'description', 'created_at']
    list_filter = ['is_active']
    search_fields = ['name']
    list_editable = ['sort_order', 'is_active']
    ordering = ['sort_order']


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'phone', 'is_active', 'models_count', 'created_at']
    list_filter = ['is_active']
    search_fields = ['code', 'name', 'phone']
    list_editable = ['is_active']
    ordering = ['name']
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = [
        ('معلومات العميل', {'fields': ['code', 'name', 'phone', 'is_active']}),
        ('التواريخ', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def models_count(self, obj):
        return obj.product_models.count()
    models_count.short_description = 'عدد الموديلات'


class ProductModelStageInline(admin.TabularInline):
    model = ProductModelStage
    extra = 0
    fields = ['stage', 'unit_price', 'sort_order', 'is_active']
    autocomplete_fields = ['stage']


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ['sku', 'color', 'size', 'planned_quantity', 'is_active']
    readonly_fields = ['sku']
    autocomplete_fields = ['color', 'size']


@admin.register(ProductModel)
class ProductModelAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'client', 'variants_count', 'total_planned', 'is_active', 'created_at']
    list_filter = ['is_active', 'client']
    search_fields = ['code', 'name', 'client__name']
    list_editable = ['is_active']
    ordering = ['code']
    readonly_fields = ['created_at', 'updated_at']
    autocomplete_fields = ['client']
    filter_horizontal = ['colors', 'sizes']
    inlines = [ProductModelStageInline, ProductVariantInline]

    fieldsets = [
        ('معلومات الموديل', {'fields': ['code', 'name', 'client', 'description', 'is_active']}),
        ('الألوان والمقاسات', {'fields': ['colors', 'sizes']}),
        ('التواريخ', {'fields': ['created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def variants_count(self, obj):
        return obj.variants.count()
    variants_count.short_description = 'أنواع المنتج'

    def total_planned(self, obj):
        return obj.total_planned
    total_planned.short_description = 'إجمالي المخطط'


@admin.register(ProductModelStage)
class ProductModelStageAdmin(admin.ModelAdmin):
    list_display = ['product_model', 'stage', 'unit_price', 'sort_order', 'is_active']
    list_filter = ['is_active', 'stage']
    search_fields = ['product_model__code', 'product_model__name', 'stage__name']
    list_editable = ['unit_price', 'is_active']
    autocomplete_fields = ['product_model', 'stage']


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['sku', 'product_model', 'color', 'size', 'planned_quantity', 'is_active']
    list_filter = ['is_active', 'product_model__client', 'color', 'size']
    search_fields = ['sku', 'product_model__code', 'product_model__name']
    list_editable = ['planned_quantity', 'is_active']
    readonly_fields = ['sku', 'created_at', 'updated_at']
    autocomplete_fields = ['product_model', 'color', 'size']
    ordering = ['product_model__code', 'color__name', 'size__sort_order']
