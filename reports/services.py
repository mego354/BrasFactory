"""Reports services — centralized aggregation queries (Layer 3: Financial)."""
from django.db.models import Sum, Count, Q, F
from production.models import ProductionEntry
from catalog.models import ProductModel, Client, ProductionStage
from workers.models import Worker


def _base_qs(filters: dict):
    """Apply common filters to ProductionEntry queryset."""
    qs = ProductionEntry.objects.filter(is_cancelled=False)
    if filters.get('start_date'):
        qs = qs.filter(production_date__gte=filters['start_date'])
    if filters.get('end_date'):
        qs = qs.filter(production_date__lte=filters['end_date'])
    if filters.get('client_id'):
        qs = qs.filter(variant__product_model__client_id=filters['client_id'])
    if filters.get('model_id'):
        qs = qs.filter(variant__product_model_id=filters['model_id'])
    if filters.get('stage_id'):
        qs = qs.filter(stage_id=filters['stage_id'])
    if filters.get('worker_id'):
        qs = qs.filter(worker_id=filters['worker_id'])
    return qs


def production_by_model(filters: dict):
    """Aggregated production data grouped by product model."""
    qs = _base_qs(filters)
    return qs.values(
        'variant__product_model__id',
        'variant__product_model__code',
        'variant__product_model__name',
        'variant__product_model__client__name',
    ).annotate(
        total_qty=Sum('quantity'),
        total_value=Sum('total_amount'),
    ).order_by('-total_qty')


def production_by_worker(filters: dict):
    """Aggregated production grouped by worker."""
    qs = _base_qs(filters)
    return qs.values(
        'worker__id', 'worker__name'
    ).annotate(
        total_qty=Sum('quantity'),
        total_earnings=Sum('total_amount'),
        entry_count=Count('id'),
    ).order_by('-total_qty')


def production_by_client(filters: dict):
    """Aggregated production grouped by client."""
    qs = _base_qs(filters)
    return qs.values(
        'variant__product_model__client__id',
        'variant__product_model__client__name',
        'variant__product_model__client__code',
    ).annotate(
        total_qty=Sum('quantity'),
        total_value=Sum('total_amount'),
        model_count=Count('variant__product_model', distinct=True),
    ).order_by('-total_value')


def production_by_stage(filters: dict):
    """Aggregated production grouped by stage."""
    qs = _base_qs(filters)
    return qs.values(
        'stage__id', 'stage__name'
    ).annotate(
        total_qty=Sum('quantity'),
        total_cost=Sum('total_amount'),
        worker_count=Count('worker', distinct=True),
    ).order_by('stage__sort_order')


def overall_summary(filters: dict) -> dict:
    """Overall totals for the report header."""
    qs = _base_qs(filters)
    agg = qs.aggregate(
        total_qty=Sum('quantity'),
        total_value=Sum('total_amount'),
        entry_count=Count('id'),
    )
    return {
        'total_qty': agg['total_qty'] or 0,
        'total_value': agg['total_value'] or 0,
        'entry_count': agg['entry_count'] or 0,
    }
