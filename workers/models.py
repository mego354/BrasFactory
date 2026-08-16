from django.db import models
from catalog.models import ProductionStage, TimestampMixin
from django.core.validators import RegexValidator

phone_validator = RegexValidator(
    regex=r'^\+?[0-9\s\-]{7,20}$',
    message='أدخل رقم هاتف صحيح.'
)


class Worker(TimestampMixin):
    name = models.CharField(max_length=100, verbose_name='اسم العامل')
    phone = models.CharField(
        max_length=20, validators=[phone_validator],
        verbose_name='رقم الهاتف'
    )
    stages = models.ManyToManyField(
        ProductionStage,
        blank=True,
        verbose_name='المراحل المسندة',
        related_name='workers'
    )
    is_active = models.BooleanField(default=True, verbose_name='نشط')
    notes = models.TextField(blank=True, verbose_name='ملاحظات')

    class Meta:
        verbose_name = 'عامل'
        verbose_name_plural = 'العمال'
        ordering = ['name']

    def __str__(self):
        return self.name
