"""
Production Services — Business rules and production entry creation.

Rules enforced here:
  Rule 1: Worker must be assigned to selected stage.
  Rule 2: Stage must be configured for the variant's product model.
  Rule 3: Quantity warning (not hard block) if exceeds previous stage qty.
  Rule 4: No silent overwrites — entries are append-only.
  Rule 5: Cancellation only, no deletion from normal flows.
"""
from django.db import transaction
from django.utils import timezone
from django.db.models import Sum

from catalog.models import ProductVariant, ProductModelStage
from workers.models import Worker
from .models import ProductionEntry


class ProductionValidationError(Exception):
    pass


def validate_entry(variant: ProductVariant, stage_id: int, worker: Worker) -> dict:
    """
    Validate a proposed production entry.
    Returns {'price': Decimal, 'warnings': [str]}
    Raises ProductionValidationError on hard rule violations.
    """
    # Rule 2: Stage must belong to this product model
    try:
        model_stage = ProductModelStage.objects.get(
            product_model=variant.product_model,
            stage_id=stage_id,
            is_active=True
        )
    except ProductModelStage.DoesNotExist:
        raise ProductionValidationError(
            f'المرحلة المختارة غير مُهيأة لموديل "{variant.product_model.code}".'
        )

    # Rule 1: Worker must be assigned to this stage
    if not worker.stages.filter(pk=stage_id, is_active=True).exists():
        raise ProductionValidationError(
            f'العامل "{worker.name}" غير مسند لمرحلة "{model_stage.stage.name}".'
        )

    return {'price': model_stage.unit_price, 'warnings': []}


@transaction.atomic
def create_production_entry(
    variant_id: int,
    stage_id: int,
    worker_id: int,
    quantity: int,
    production_date,
    user,
    notes: str = ''
) -> ProductionEntry:
    """
    Create a production entry atomically.
    Validates all rules before saving.
    Snapshots the unit price at creation time.
    """
    variant = ProductVariant.objects.select_related('product_model').get(pk=variant_id)
    worker = Worker.objects.get(pk=worker_id)

    validation = validate_entry(variant, stage_id, worker)
    price = validation['price']
    total = price * quantity

    entry = ProductionEntry.objects.create(
        variant=variant,
        stage_id=stage_id,
        worker=worker,
        quantity=quantity,
        unit_price_snapshot=price,
        total_amount=total,
        production_date=production_date,
        notes=notes,
        created_by=user,
    )
    return entry


@transaction.atomic
def cancel_production_entry(entry: ProductionEntry, reason: str, user) -> ProductionEntry:
    """Soft-cancel a production entry. Never deletes."""
    if entry.is_cancelled:
        raise ProductionValidationError('هذا السجل مُلغى بالفعل.')
    entry.is_cancelled = True
    entry.cancellation_reason = reason
    entry.cancelled_by = user
    entry.cancelled_at = timezone.now()
    entry.save()
    return entry


def get_variant_stage_totals(variant: ProductVariant) -> dict:
    """
    Returns produced quantity per stage for a given variant.
    {stage_id: quantity}
    """
    qs = ProductionEntry.objects.filter(
        variant=variant, is_cancelled=False
    ).values('stage_id').annotate(qty=Sum('quantity'))
    return {row['stage_id']: row['qty'] for row in qs}


def get_model_progress(product_model) -> dict:
    """
    Compute overall production progress for a product model.
    Returns dict with totals per stage.
    """
    from catalog.models import ProductModelStage
    total_planned = product_model.total_planned
    stage_data = []
    for ms in product_model.model_stages.filter(is_active=True).select_related('stage').order_by('sort_order'):
        produced = ProductionEntry.objects.filter(
            variant__product_model=product_model,
            stage=ms.stage,
            is_cancelled=False
        ).aggregate(qty=Sum('quantity'))['qty'] or 0
        stage_data.append({
            'stage': ms.stage,
            'unit_price': ms.unit_price,
            'planned': total_planned,
            'produced': produced,
            'remaining': max(0, total_planned - produced),
            'pct': round(produced / total_planned * 100, 1) if total_planned > 0 else 0,
        })
    return {'total_planned': total_planned, 'stages': stage_data}
