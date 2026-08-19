"""
Production Models — Layer 2: Production Activity

ProductionEntry is an append-only record. Never edit, only cancel.
"""
from django.db import models
from django.contrib.auth.models import User
from catalog.models import ProductVariant, ProductionStage
from workers.models import Worker


class ProductionEntry(models.Model):
    """
    Immutable production history record.
    Represents: Worker produced N pieces of Variant at Stage on Date.
    unit_price_snapshot is frozen at creation time.
    """
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.PROTECT,
        related_name='entries', verbose_name='نوع المنتج'
    )
    stage = models.ForeignKey(
        ProductionStage, on_delete=models.PROTECT,
        related_name='entries', verbose_name='المرحلة'
    )
    worker = models.ForeignKey(
        Worker, on_delete=models.PROTECT,
        related_name='entries', verbose_name='العامل'
    )
    quantity = models.PositiveIntegerField(verbose_name='الكمية')
    unit_price_snapshot = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name='سعر الوحدة (مُثبَّت)'
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name='الإجمالي'
    )
    production_date = models.DateField(verbose_name='تاريخ الإنتاج')
    notes = models.TextField(blank=True, verbose_name='ملاحظات')

    # Audit
    entered_by_worker = models.BooleanField(default=False, verbose_name='إدخال ذاتي بواسطة العامل')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='created_entries',
        verbose_name='أُنشئ بواسطة'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاريخ الإنشاء')

    # Cancellation (soft delete)
    is_cancelled = models.BooleanField(default=False, verbose_name='ملغى')
    cancellation_reason = models.TextField(blank=True, verbose_name='سبب الإلغاء')
    cancelled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='cancelled_entries',
        verbose_name='ألغاه'
    )
    cancelled_at = models.DateTimeField(null=True, blank=True, verbose_name='تاريخ الإلغاء')

    class Meta:
        verbose_name = 'سجل إنتاج'
        verbose_name_plural = 'سجلات الإنتاج'
        ordering = ['-production_date', '-created_at']
        indexes = [
            models.Index(fields=['variant', 'stage']),
            models.Index(fields=['worker', 'production_date']),
            models.Index(fields=['production_date']),
            models.Index(fields=['is_cancelled']),
        ]

    def __str__(self):
        return f"{self.production_date} | {self.variant} | {self.stage} | {self.worker} | {self.quantity}"

    @property
    def is_active(self):
        return not self.is_cancelled
