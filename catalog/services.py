"""
Catalog Services — Business logic for product definition layer and QR code generation.
"""
import re
import io
import base64
import qrcode
from django.db import transaction
from django.urls import reverse
from .models import ProductModel, ProductVariant, ProductModelStage


def generate_sku(model_code: str, color_name: str, size_name: str) -> str:
    """
    Generate a deterministic SKU from model code + color + size.
    Example: BR100 + Black + M → BR100-BLK-M
    """
    def slugify_part(s: str, max_len: int = 5) -> str:
        s = re.sub(r'[^a-zA-Z0-9\u0600-\u06FF]', '', s).upper()
        return s[:max_len]

    model_part = slugify_part(model_code, 6)
    color_part = slugify_part(color_name, 4)
    size_part = slugify_part(size_name, 4)
    return f"{model_part}-{color_part}-{size_part}"


def generate_variants(product_model: ProductModel, quantities: dict = None) -> tuple[int, int]:
    """
    Generate or update ProductVariant records for all Color × Size combinations.
    quantities: optional dict mapping 'colorId__sizeId' -> planned_quantity integer.
    Returns (created_count, existing_count).
    """
    created = 0
    existing = 0
    colors = product_model.colors.filter(is_active=True)
    sizes = product_model.sizes.filter(is_active=True)
    quantities = quantities or {}

    with transaction.atomic():
        for color in colors:
            for size in sizes:
                sku = generate_sku(product_model.code, color.name, size.name)
                # Ensure SKU uniqueness across all models
                base_sku = sku
                counter = 1
                while ProductVariant.objects.filter(sku=sku).exclude(
                    product_model=product_model, color=color, size=size
                ).exists():
                    sku = f"{base_sku}-{counter}"
                    counter += 1

                qty_key = f"{color.pk}__{size.pk}"
                planned_qty = int(quantities.get(qty_key, 0))

                variant, was_created = ProductVariant.objects.get_or_create(
                    product_model=product_model,
                    color=color,
                    size=size,
                    defaults={'sku': sku, 'planned_quantity': planned_qty}
                )
                if was_created:
                    created += 1
                else:
                    # Update planned quantity if provided
                    if qty_key in quantities:
                        variant.planned_quantity = planned_qty
                        variant.save(update_fields=['planned_quantity'])
                    existing += 1

    return created, existing


def get_model_stage_price(product_model: ProductModel, stage_id: int):
    """
    Safely retrieve the unit price for a stage on a specific model.
    Returns the price or None.
    """
    ms = ProductModelStage.objects.filter(
        product_model=product_model,
        stage_id=stage_id,
        is_active=True
    ).first()
    return ms.unit_price if ms else None


# ============================================================
# QR Code Services
# ============================================================
def build_model_entry_url(model: ProductModel, base_url: str = 'http://127.0.0.1:8000') -> str:
    """
    Build the target URL for registering production for this model (pre-fills client and model).
    """
    client_id = model.client_id
    model_id = model.id
    path = reverse('production:entry')
    return f"{base_url.rstrip('/')}{path}?client={client_id}&model={model_id}"


def build_variant_entry_url(variant: ProductVariant, base_url: str = 'http://127.0.0.1:8000') -> str:
    """
    Build the target URL for registering production for this specific variant.
    Includes client, model, variant parameters.
    """
    client_id = variant.product_model.client_id
    model_id = variant.product_model_id
    variant_id = variant.id
    path = reverse('production:entry')
    return f"{base_url.rstrip('/')}{path}?client={client_id}&model={model_id}&variant={variant_id}"


def generate_qr_png_bytes(data: str) -> bytes:
    """Generate PNG bytes for any data string."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


def generate_qr_base64(data: str) -> str:
    """Generate base64 data URI (data:image/png;base64,...) for direct inline HTML embedding."""
    raw_bytes = generate_qr_png_bytes(data)
    b64_str = base64.b64encode(raw_bytes).decode('utf-8')
    return f"data:image/png;base64,{b64_str}"


# ============================================================
# Client Reporting Services (Matching Worker Services)
# ============================================================
def get_client_production_summary(client, start_date=None, end_date=None, model_id=None, stage_id=None):
    """Return production earnings/financial summary for a client with optional filters."""
    from production.models import ProductionEntry
    from django.db.models import Sum, Count

    qs = ProductionEntry.objects.filter(
        variant__product_model__client=client,
        is_cancelled=False
    )
    if start_date:
        qs = qs.filter(production_date__gte=start_date)
    if end_date:
        qs = qs.filter(production_date__lte=end_date)
    if model_id:
        qs = qs.filter(variant__product_model_id=model_id)
    if stage_id:
        qs = qs.filter(stage_id=stage_id)

    agg = qs.aggregate(
        total_qty=Sum('quantity'),
        total_amount=Sum('total_amount'),
        entry_count=Count('id')
    )
    return {
        'total_qty': agg['total_qty'] or 0,
        'total_amount': agg['total_amount'] or 0,
        'entry_count': agg['entry_count'] or 0,
        'models_count': client.product_models.count(),
    }


def get_client_production_history(client, start_date=None, end_date=None, model_id=None, stage_id=None):
    """Return detailed production entries for a client with related objects."""
    from production.models import ProductionEntry

    qs = ProductionEntry.objects.filter(
        variant__product_model__client=client,
        is_cancelled=False
    ).select_related(
        'variant__product_model',
        'variant__color', 'variant__size',
        'stage',
        'worker'
    ).order_by('-production_date', '-created_at')

    if start_date:
        qs = qs.filter(production_date__gte=start_date)
    if end_date:
        qs = qs.filter(production_date__lte=end_date)
    if model_id:
        qs = qs.filter(variant__product_model_id=model_id)
    if stage_id:
        qs = qs.filter(stage_id=stage_id)
    return qs


def get_client_variant_breakdown(client, start_date=None, end_date=None, model_id=None):
    """
    Return aggregated production summary grouped by model, color, size and stage for this client.
    """
    from production.models import ProductionEntry
    from django.db.models import Sum

    qs = ProductionEntry.objects.filter(
        variant__product_model__client=client,
        is_cancelled=False
    )
    if start_date:
        qs = qs.filter(production_date__gte=start_date)
    if end_date:
        qs = qs.filter(production_date__lte=end_date)
    if model_id:
        qs = qs.filter(variant__product_model_id=model_id)

    breakdown = qs.values(
        'variant__product_model__id',
        'variant__product_model__code',
        'variant__product_model__name',
        'variant__color__name',
        'variant__size__name',
        'stage__name',
        'unit_price_snapshot'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_value=Sum('total_amount')
    ).order_by('variant__product_model__code', 'variant__color__name', 'variant__size__name', 'stage__name')

    return list(breakdown)


def get_client_models_progress(client, start_date=None, end_date=None):
    """
    Return all models for the client with stage-level planned vs produced progress.
    """
    from production.models import ProductionEntry
    from django.db.models import Sum

    models = client.product_models.prefetch_related('model_stages__stage', 'variants').filter(is_active=True).order_by('-created_at')
    result = []

    for m in models:
        planned = m.total_planned
        stages_data = []
        for ms in m.model_stages.filter(is_active=True).select_related('stage').order_by('sort_order'):
            entry_qs = ProductionEntry.objects.filter(
                variant__product_model=m,
                stage=ms.stage,
                is_cancelled=False
            )
            if start_date:
                entry_qs = entry_qs.filter(production_date__gte=start_date)
            if end_date:
                entry_qs = entry_qs.filter(production_date__lte=end_date)

            prod = entry_qs.aggregate(t=Sum('quantity'))['t'] or 0
            val = entry_qs.aggregate(t=Sum('total_amount'))['t'] or 0
            pct = min(100, int((prod / planned * 100))) if planned > 0 else 0
            stages_data.append({
                'stage': ms.stage,
                'name': ms.stage.name,
                'produced': prod,
                'total_value': val,
                'unit_price': ms.unit_price,
                'pct': pct,
            })

        result.append({
            'model': m,
            'planned': planned,
            'stages': stages_data,
        })
    return result

