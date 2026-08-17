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
from core.utils import get_current_month_date_range
from core.pdf import FactoryPDFReport, generate_qr_image_flowable
from catalog.models import Client, ProductModel, ProductVariant, ProductionStage, ProductModelStage
from catalog.services import build_variant_entry_url, build_model_entry_url
from workers.models import Worker
from .models import ProductionEntry
from .forms import ProductionEntryForm, CancelEntryForm
from .services import create_production_entry, cancel_production_entry, ProductionValidationError
from django.conf import settings


# ─────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────
@method_decorator(login_required, name='dispatch')
class DashboardView(View):
    def get(self, request):
        # Filters
        client_id = request.GET.get('client', '')
        start_date, end_date = get_current_month_date_range(
            request.GET.get('start_date'),
            request.GET.get('end_date')
        )

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

        if request.GET.get('export') == 'pdf':
            pdf = FactoryPDFReport(
                title='تقرير متابعة وسجل الإنتاج العام للمصنع',
                subtitle=f'الفترة من {start_date} إلى {end_date}'
            )
            base_url = request.build_absolute_uri('/')
            pdf.add_header(filters_dict={
                'الفترة': f'{start_date} إلى {end_date}',
                'العميل': Client.objects.get(pk=client_id).name if client_id else 'كل العملاء',
            })
            pdf.add_kpis([
                ('إجمالي الإنتاج الفعلي', f"{total_produced:,} قطعة"),
                ('إجمالي القيمة المالية', f"{total_value:,.2f} ج.م"),
                ('الموديلات النشطة', f"{active_models:,} موديل"),
                ('العمال النشطون', f"{active_workers:,} عامل"),
            ])

            # Model Progress Table with Register QR codes
            if model_progress:
                pdf.add_section_title('موقف إنتاج الموديلات الحالية وأكواد QR للتسجيل')
                m_rows = []
                for mp in model_progress:
                    pm_obj = mp['model']
                    qr_img = generate_qr_image_flowable(build_model_entry_url(pm_obj, base_url), size=28)
                    m_rows.append([
                        pm_obj.code,
                        pm_obj.name,
                        pm_obj.client.name,
                        f"{mp['planned']:,}",
                        f"{mp['overall_pct']}%",
                        qr_img,
                    ])
                pdf.add_table(
                    headers=['الكود', 'اسم الموديل', 'العميل', 'المخطط', 'الإنجاز', 'رمز QR'],
                    rows=m_rows,
                    col_widths=[75, 140, 120, 70, 65, 65],
                    right_align_cols=[1, 2]
                )

            # Recent Production Entries with Variant Register QR codes
            recent_entries_full = entries_qs.select_related(
                'variant__product_model__client', 'variant__color', 'variant__size',
                'stage', 'worker'
            ).order_by('-production_date', '-created_at')[:35]

            if recent_entries_full:
                pdf.add_section_title('سجلات الإنتاج التفصيلية مع أكواد QR للأنواع (Variants)')
                entry_rows = []
                for e in recent_entries_full:
                    v_qr = generate_qr_image_flowable(build_variant_entry_url(e.variant, base_url), size=26)
                    entry_rows.append([
                        str(e.production_date),
                        e.variant.product_model.code,
                        f"{e.variant.color.name} / {e.variant.size.name}",
                        e.stage.name,
                        e.worker.name,
                        f"{e.quantity:,}",
                        f"{e.total_amount:,.2f} ج.م",
                        v_qr,
                    ])
                pdf.add_table(
                    headers=['التاريخ', 'الموديل', 'النوع', 'المرحلة', 'العامل', 'الكمية', 'الإجمالي', 'رمز QR'],
                    rows=entry_rows,
                    col_widths=[58, 55, 95, 85, 80, 42, 60, 60],
                    right_align_cols=[1, 2, 3, 4]
                )

            return pdf.build_response(f'production_report_{start_date}_{end_date}.pdf')

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
# Production Entry (with Unauthenticated QR Pre-Data Preview)
# ─────────────────────────────────────────────
class ProductionEntryView(View):
    template_name = 'production/entry.html'

    def get(self, request):
        initial_variant_id = request.GET.get('variant', '')
        initial_model_id = request.GET.get('model', '')
        initial_client_id = request.GET.get('client', '')
        initial_date = request.GET.get('date', '')

        # Resolve variant, model, and client if provided
        variant_obj = None
        model_obj = None
        if initial_variant_id:
            try:
                variant_obj = ProductVariant.objects.select_related('product_model__client', 'color', 'size').get(pk=initial_variant_id)
                model_obj = variant_obj.product_model
                initial_model_id = str(model_obj.pk)
                initial_client_id = str(model_obj.client_id)
            except ProductVariant.DoesNotExist:
                pass
        elif initial_model_id:
            try:
                model_obj = ProductModel.objects.select_related('client').prefetch_related('model_stages__stage', 'variants').get(pk=initial_model_id)
                if not initial_client_id:
                    initial_client_id = str(model_obj.client_id)
            except ProductModel.DoesNotExist:
                pass

        # If user is NOT logged in: Show Pre-Data Specs preview card for QR scan
        if not request.user.is_authenticated:
            if model_obj or variant_obj:
                total_planned = variant_obj.planned_quantity if variant_obj else model_obj.total_planned
                prod_qs = ProductionEntry.objects.filter(is_cancelled=False)
                if variant_obj:
                    prod_qs = prod_qs.filter(variant=variant_obj)
                else:
                    prod_qs = prod_qs.filter(variant__product_model=model_obj)
                total_produced = prod_qs.aggregate(q=Sum('quantity'))['q'] or 0

                return render(request, 'production/item_preview.html', {
                    'model': model_obj,
                    'variant': variant_obj,
                    'total_planned': total_planned,
                    'total_produced': total_produced,
                })
            else:
                login_url = getattr(settings, 'LOGIN_URL', '/auth/login/')
                return redirect(f"{login_url}?next={request.get_full_path()}")

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
        if not request.user.is_authenticated:
            login_url = getattr(settings, 'LOGIN_URL', '/auth/login/')
            return redirect(f"{login_url}?next={request.get_full_path()}")

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
