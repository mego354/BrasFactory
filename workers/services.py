"""Worker services — earnings and production summary queries."""
from django.db.models import Sum, Count, Q


def get_worker_earnings(worker, start_date=None, end_date=None, stage_id=None, client_id=None):
    """Return earnings summary for a worker with optional filters."""
    from production.models import ProductionEntry
    qs = ProductionEntry.objects.filter(worker=worker, is_cancelled=False)
    if start_date:
        qs = qs.filter(production_date__gte=start_date)
    if end_date:
        qs = qs.filter(production_date__lte=end_date)
    if stage_id:
        qs = qs.filter(stage_id=stage_id)
    if client_id:
        qs = qs.filter(variant__product_model__client_id=client_id)

    agg = qs.aggregate(
        total_qty=Sum('quantity'),
        total_amount=Sum('total_amount'),
        entry_count=Count('id')
    )
    return {
        'total_qty': agg['total_qty'] or 0,
        'total_amount': agg['total_amount'] or 0,
        'entry_count': agg['entry_count'] or 0,
    }


def get_worker_production_history(worker, start_date=None, end_date=None, stage_id=None):
    """Return detailed production entries for a worker."""
    from production.models import ProductionEntry
    qs = ProductionEntry.objects.filter(
        worker=worker, is_cancelled=False
    ).select_related(
        'variant__product_model',
        'variant__color', 'variant__size',
        'stage'
    ).order_by('-production_date', '-created_at')
    if start_date:
        qs = qs.filter(production_date__gte=start_date)
    if end_date:
        qs = qs.filter(production_date__lte=end_date)
    if stage_id:
        qs = qs.filter(stage_id=stage_id)
    return qs


def get_worker_variant_breakdown(worker, start_date=None, end_date=None):
    """
    Return aggregated production summary grouped by variant (model, color, size) and stage (skill).
    """
    from production.models import ProductionEntry
    qs = ProductionEntry.objects.filter(worker=worker, is_cancelled=False)
    if start_date:
        qs = qs.filter(production_date__gte=start_date)
    if end_date:
        qs = qs.filter(production_date__lte=end_date)

    breakdown = qs.values(
        'variant__product_model__code',
        'variant__product_model__name',
        'variant__color__name',
        'variant__size__name',
        'stage__name',
        'unit_price_snapshot'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_earnings=Sum('total_amount')
    ).order_by('variant__product_model__code', 'stage__name', 'variant__color__name')

    return list(breakdown)

