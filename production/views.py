"""
Production Views — Dashboard, Entry, AJAX endpoints.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.http import JsonResponse
from django.db.models import Q, Sum, Count
from django.core.paginator import Paginator
from django.utils import timezone

from core.mixins import LoginRequiredMixin
from catalog.models import Client, ProductModel, ProductVariant, ProductionStage, ProductModelStage
from workers.models import Worker
from .models import ProductionEntry
from .forms import ProductionEntryForm, CancelEntryForm
from .services import create_production_entry, cancel_production_entry, ProductionValidationError


# ─────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────
@method_decorator(login_required, name='dispatch')
class DashboardView(View):
    def get(self, request):
        # Filters
        client_id = request.GET.get('client', '')
        start_date = request.GET.get('start_date', '')
        end_date = request.GET.get('end_date', '')

        entries_qs = ProductionEntry.objects.filter(is_cancelled=False)
        if client_id:
            entries_qs = entries_qs.filter(variant__product_model__client_id=client_id)
        if start_date:
            entries_qs = entries_qs.filter(production_date__gte=start_date)
        if end_date:
            entries_qs = entries_qs.filter(production_date__lte=end_date)

        # Summary cards
        total_produced = entries_qs.aggregate(qty=Sum('quantity'))['qty'] or 0
        total_value = entries_qs.aggregate(val=Sum('total_amount'))['val'] or 0
        total_planned = ProductVariant.objects.filter(is_active=True).aggregate(
            qty=Sum('planned_quantity')
        )['qty'] or 0
        active_models = ProductModel.objects.filter(is_active=True).count()
        active_workers = Worker.objects.filter(is_active=True).count()
        active_clients = Client.objects.filter(is_active=True).count()

        # Active product models with progress
        models_qs = ProductModel.objects.filter(is_active=True).select_related('client').prefetch_related(
            'variants', 'model_stages__stage'
        )
        if client_id:
            models_qs = models_qs.filter(client_id=client_id)

        model_progress = []
        for pm in models_qs[:12]:
            planned = pm.total_planned
            stages_info = []
            for ms in pm.model_stages.filter(is_active=True).select_related('stage').order_by('sort_order'):
                produced_qty = ProductionEntry.objects.filter(
                    variant__product_model=pm,
                    stage=ms.stage,
                    is_cancelled=False
                ).aggregate(qty=Sum('quantity'))['qty'] or 0
                stages_info.append({
                    'name': ms.stage.name,
                    'produced': produced_qty,
                    'pct': round(produced_qty / planned * 100, 1) if planned > 0 else 0,
                })
            overall_pct = 0
            if stages_info:
                overall_pct = round(sum(s['pct'] for s in stages_info) / len(stages_info), 1)
            model_progress.append({
                'model': pm,
                'planned': planned,
                'stages': stages_info,
                'overall_pct': overall_pct,
            })

        # Recent entries
        recent = ProductionEntry.objects.filter(is_cancelled=False).select_related(
            'variant__product_model__client', 'variant__color', 'variant__size',
            'stage', 'worker'
        ).order_by('-created_at')[:10]

        # Top workers today
        today = timezone.localdate()
        top_workers = ProductionEntry.objects.filter(
            is_cancelled=False, production_date=today
        ).values('worker__name').annotate(
            qty=Sum('quantity'), earnings=Sum('total_amount')
        ).order_by('-qty')[:5]

        clients = Client.objects.filter(is_active=True)

        return render(request, 'production/dashboard.html', {
            'total_produced': total_produced,
            'total_value': total_value,
            'total_planned': total_planned,
            'active_models': active_models,
            'active_workers': active_workers,
            'active_clients': active_clients,
            'model_progress': model_progress,
            'recent': recent,
            'top_workers': top_workers,
            'clients': clients,
            'client_id': client_id,
            'start_date': start_date,
            'end_date': end_date,
        })


# ─────────────────────────────────────────────
# Production Entry
# ─────────────────────────────────────────────
@method_decorator(login_required, name='dispatch')
class ProductionEntryView(View):
    template_name = 'production/entry.html'

    def get(self, request):
        initial_variant_id = request.GET.get('variant', '')
        initial_model_id = request.GET.get('model', '')
        initial_client_id = request.GET.get('client', '')
        initial_date = request.GET.get('date', '')

        # If variant_id is provided, resolve model and client
        if initial_variant_id:
            try:
                v = ProductVariant.objects.select_related('product_model__client').get(pk=initial_variant_id)
                initial_model_id = str(v.product_model_id)
                initial_client_id = str(v.product_model.client_id)
            except ProductVariant.DoesNotExist:
                pass
        elif initial_model_id and not initial_client_id:
            try:
                m = ProductModel.objects.get(pk=initial_model_id)
                initial_client_id = str(m.client_id)
            except ProductModel.DoesNotExist:
                pass

        today_date = timezone.localdate().isoformat()
        form_initial = {'production_date': initial_date if initial_date else today_date}
        form = ProductionEntryForm(initial=form_initial)
        recent = ProductionEntry.objects.filter(
            is_cancelled=False
        ).select_related(
            'variant__product_model__client',
            'variant__color', 'variant__size',
            'stage', 'worker', 'created_by'
        ).order_by('-created_at')[:15]

        clients = Client.objects.filter(is_active=True)
        return render(request, self.template_name, {
            'form': form,
            'recent': recent,
            'clients': clients,
            'today_date': today_date,
            'initial_client_id': initial_client_id,
            'initial_model_id': initial_model_id,
            'initial_variant_id': initial_variant_id,
        })

    def post(self, request):
        form = ProductionEntryForm(request.POST)
        clients = Client.objects.filter(is_active=True)
        recent = ProductionEntry.objects.filter(is_cancelled=False).select_related(
            'variant__product_model__client', 'variant__color', 'variant__size',
            'stage', 'worker'
        ).order_by('-created_at')[:15]

        if form.is_valid():
            try:
                entry = create_production_entry(
                    variant_id=form.cleaned_data['variant'].pk,
                    stage_id=form.cleaned_data['stage'].pk,
                    worker_id=form.cleaned_data['worker'].pk,
                    quantity=form.cleaned_data['quantity'],
                    production_date=form.cleaned_data['production_date'],
                    user=request.user,
                    notes=form.cleaned_data.get('notes', ''),
                )
                messages.success(
                    request,
                    f'✅ تم تسجيل إنتاج {entry.quantity} قطعة بنجاح. '
                    f'الإجمالي: {entry.total_amount:.2f} ج.م'
                )
                return redirect('production:entry')
            except ProductionValidationError as e:
                messages.error(request, str(e))
            except Exception as e:
                messages.error(request, f'خطأ غير متوقع: {e}')

        return render(request, self.template_name, {
            'form': form, 'recent': recent, 'clients': clients,
        })


# ─────────────────────────────────────────────
# Cancel Entry
# ─────────────────────────────────────────────
@method_decorator(login_required, name='dispatch')
class CancelEntryView(View):
    def post(self, request, pk):
        entry = get_object_or_404(ProductionEntry, pk=pk)
        form = CancelEntryForm(request.POST)
        if form.is_valid():
            if not request.user.is_staff:
                messages.error(request, 'فقط المشرفون يمكنهم إلغاء سجلات الإنتاج.')
                return redirect('production:entry')
            try:
                cancel_production_entry(entry, form.cleaned_data['reason'], request.user)
                messages.success(request, 'تم إلغاء سجل الإنتاج بنجاح.')
            except ProductionValidationError as e:
                messages.error(request, str(e))
        else:
            messages.error(request, 'يرجى إدخال سبب الإلغاء.')
        return redirect(request.META.get('HTTP_REFERER', 'production:entry'))


# ─────────────────────────────────────────────
# AJAX Endpoints
# ─────────────────────────────────────────────
@login_required
def ajax_models_by_client(request):
    client_id = request.GET.get('client_id')
    if not client_id:
        return JsonResponse({'models': []})
    models = ProductModel.objects.filter(
        client_id=client_id, is_active=True
    ).values('id', 'code', 'name').order_by('code')
    return JsonResponse({
        'models': [{'id': m['id'], 'name': f"{m['code']} — {m['name']}"} for m in models]
    })


@login_required
def ajax_variants_by_model(request):
    model_id = request.GET.get('model_id')
    if not model_id:
        return JsonResponse({'variants': []})
    variants = ProductVariant.objects.filter(
        product_model_id=model_id, is_active=True
    ).select_related('color', 'size').order_by('color__name', 'size__sort_order')
    return JsonResponse({
        'variants': [
            {'id': v.id, 'name': f"{v.color.name} / {v.size.name} (مخطط: {v.planned_quantity})"}
            for v in variants
        ]
    })


@login_required
def ajax_stages_by_variant(request):
    variant_id = request.GET.get('variant_id')
    if not variant_id:
        return JsonResponse({'stages': []})
    try:
        variant = ProductVariant.objects.get(pk=variant_id)
    except ProductVariant.DoesNotExist:
        return JsonResponse({'stages': []})
    stages = ProductModelStage.objects.filter(
        product_model=variant.product_model, is_active=True
    ).select_related('stage').order_by('sort_order')
    return JsonResponse({
        'stages': [{'id': ms.stage.pk, 'name': ms.stage.name} for ms in stages]
    })


@login_required
def ajax_workers_by_stage(request):
    stage_id = request.GET.get('stage_id')
    if not stage_id:
        return JsonResponse({'workers': []})
    workers = Worker.objects.filter(
        stages__id=stage_id, is_active=True
    ).order_by('name')
    return JsonResponse({
        'workers': [{'id': w.pk, 'name': w.name} for w in workers]
    })


@login_required
def ajax_price_for_stage(request):
    variant_id = request.GET.get('variant_id')
    stage_id = request.GET.get('stage_id')
    if not variant_id or not stage_id:
        return JsonResponse({'unit_price': 0})
    try:
        variant = ProductVariant.objects.select_related('product_model').get(pk=variant_id)
        ms = ProductModelStage.objects.get(
            product_model=variant.product_model,
            stage_id=stage_id,
            is_active=True
        )
        return JsonResponse({'unit_price': str(ms.unit_price)})
    except (ProductVariant.DoesNotExist, ProductModelStage.DoesNotExist):
        return JsonResponse({'unit_price': 0})
