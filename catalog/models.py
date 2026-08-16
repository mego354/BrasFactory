"""
Catalog Models — Layer 1: Product Definition

Color, Size, Client, ProductionStage,
ProductModel, ProductModelStage, ProductVariant
"""
from django.db import models
from django.core.validators import RegexValidator


class TimestampMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ─────────────────────────────────────────────
# Color
# ─────────────────────────────────────────────
class Color(TimestampMixin):
    name = models.CharField(max_length=50, unique=True, verbose_name='اسم اللون')
    is_active = models.BooleanField(default=True, verbose_name='نشط')

    class Meta:
        verbose_name = 'لون'
        verbose_name_plural = 'الألوان'
        ordering = ['name']

    def __str__(self):
        return self.name


# ─────────────────────────────────────────────
# Size
# ─────────────────────────────────────────────
class Size(TimestampMixin):
    name = models.CharField(max_length=20, unique=True, verbose_name='المقاس')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='الترتيب')
    is_active = models.BooleanField(default=True, verbose_name='نشط')

    class Meta:
        verbose_name = 'مقاس'
        verbose_name_plural = 'المقاسات'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


# ─────────────────────────────────────────────
# Production Stage
# ─────────────────────────────────────────────
class ProductionStage(TimestampMixin):
    name = models.CharField(max_length=100, unique=True, verbose_name='اسم المرحلة')
    description = models.TextField(blank=True, verbose_name='الوصف')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='الترتيب')
    is_active = models.BooleanField(default=True, verbose_name='نشط')

    class Meta:
        verbose_name = 'مرحلة الإنتاج'
        verbose_name_plural = 'مراحل الإنتاج'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


# ─────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────
phone_validator = RegexValidator(
    regex=r'^\+?[0-9\s\-]{7,20}$',
    message='أدخل رقم هاتف صحيح.'
)


class Client(TimestampMixin):
    code = models.CharField(max_length=20, unique=True, verbose_name='كود العميل')
    name = models.CharField(max_length=100, verbose_name='اسم العميل')
    phone = models.CharField(
        max_length=20, validators=[phone_validator],
        verbose_name='رقم الهاتف'
    )
    is_active = models.BooleanField(default=True, verbose_name='نشط')

    class Meta:
        verbose_name = 'عميل'
        verbose_name_plural = 'العملاء'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


# ─────────────────────────────────────────────
# Product Model
# ─────────────────────────────────────────────
class ProductModel(TimestampMixin):
    code = models.CharField(max_length=30, unique=True, verbose_name='كود الموديل')
    name = models.CharField(max_length=100, unique=True, verbose_name='اسم الموديل')
    client = models.ForeignKey(
        Client, on_delete=models.PROTECT,
        related_name='product_models', verbose_name='العميل'
    )
    description = models.TextField(blank=True, verbose_name='الوصف')
    colors = models.ManyToManyField(Color, blank=True, verbose_name='الألوان')
    sizes = models.ManyToManyField(Size, blank=True, verbose_name='المقاسات')
    is_active = models.BooleanField(default=True, verbose_name='نشط')

    class Meta:
        verbose_name = 'موديل منتج'
        verbose_name_plural = 'موديلات المنتجات'
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def total_planned(self):
        return self.variants.filter(is_active=True).aggregate(
            total=models.Sum('planned_quantity')
        )['total'] or 0


# ─────────────────────────────────────────────
# Product Model Stage (Price per stage per model)
# ─────────────────────────────────────────────
class ProductModelStage(TimestampMixin):
    """
    Defines which stages a product model uses AND their price.
    Price is model-specific — not shared across models.
    """
    product_model = models.ForeignKey(
        ProductModel, on_delete=models.CASCADE,
        related_name='model_stages', verbose_name='الموديل'
    )
    stage = models.ForeignKey(
        ProductionStage, on_delete=models.PROTECT,
        related_name='model_configs', verbose_name='المرحلة'
    )
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        verbose_name='سعر الوحدة'
    )
    sort_order = models.PositiveIntegerField(default=0, verbose_name='الترتيب')
    is_active = models.BooleanField(default=True, verbose_name='نشط')

    class Meta:
        verbose_name = 'مرحلة الموديل'
        verbose_name_plural = 'مراحل الموديل'
        unique_together = [('product_model', 'stage')]
        ordering = ['sort_order', 'stage__sort_order']

    def __str__(self):
        return f"{self.product_model.code} → {self.stage.name} ({self.unit_price} ج.م)"


# ─────────────────────────────────────────────
# Product Variant (SKU)
# ─────────────────────────────────────────────
class ProductVariant(TimestampMixin):
    """
    One unique SKU = ProductModel + Color + Size
    Generated automatically from the model wizard.
    """
    product_model = models.ForeignKey(
        ProductModel, on_delete=models.PROTECT,
        related_name='variants', verbose_name='الموديل'
    )
    color = models.ForeignKey(
        Color, on_delete=models.PROTECT,
        verbose_name='اللون'
    )
    size = models.ForeignKey(
        Size, on_delete=models.PROTECT,
        verbose_name='المقاس'
    )
    sku = models.CharField(max_length=60, unique=True, verbose_name='كود المنتج (SKU)')
    planned_quantity = models.PositiveIntegerField(default=0, verbose_name='الكمية المخططة')
    is_active = models.BooleanField(default=True, verbose_name='نشط')

    class Meta:
        verbose_name = 'نوع المنتج'
        verbose_name_plural = 'أنواع المنتجات'
        unique_together = [('product_model', 'color', 'size')]
        ordering = ['product_model', 'color__name', 'size__sort_order']

    def __str__(self):
        return f"{self.sku} — {self.color} / {self.size}"

    @property
    def display_name(self):
        return f"{self.product_model.code} | {self.color.name} | {self.size.name}"
