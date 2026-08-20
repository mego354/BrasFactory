"""
External Views — Worker portal authenticated via Telegram magic-link.

Security: Entity identity stored ONLY in server session (set by MagicLoginView or
WorkerTelegramDirectLoginView). Never trust URL parameters for identity.

Client-facing frontend has been removed. Only worker portal remains.
"""
import calendar
from datetime import date

from django.shortcuts import render, redirect
from django.contrib import messages
from django.views import View
from django.db.models import Sum
from django.core.paginator import Paginator
from django.utils import timezone

from workers.models import Worker
from workers.services import get_worker_earnings, get_worker_production_history, get_worker_variant_breakdown
from production.models import ProductionEntry
from core.pdf import FactoryPDFReport, generate_qr_image_flowable
from catalog.services import build_variant_entry_url

EXTERNAL_SESSION_KEY = 'external_auth'

ARABIC_MONTHS = [
    '', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
    'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
]


def _get_external_entity(session):
    """Safely retrieve authenticated external entity from session."""
    return session.get(EXTERNAL_SESSION_KEY)


def _require_worker_session(request):
    """
    Returns (worker, None) if a valid worker session exists.
    Returns (None, redirect_response) otherwise.
    """
    auth = _get_external_entity(request.session)
    if not auth or auth.get('type') != 'worker':
        messages.error(request, 'رابط الدخول غير صالح أو انتهت الجلسة. يرجى طلب رابط جديد من البوت.')
        return None, redirect('accounts:login')
    try:
        worker = Worker.objects.prefetch_related('stages').get(pk=auth['entity_id'], is_active=True)
        return worker, None
    except Worker.DoesNotExist:
        request.session.pop(EXTERNAL_SESSION_KEY, None)
        messages.error(request, 'حساب العامل غير نشط.')
        return None, redirect('accounts:login')


def get_worker_period_context(period_param='this_month'):
    """
    Build period filter context strictly for:
    - 'today': Today only
    - 'this_month': Current month (default)
    - 'last_month': Previous month
    """
    today = date.today()
    period = period_param or 'this_month'

    if period == 'today':
        start_date = today
        end_date = today
        title = f'إنتاج اليوم ({today.strftime("%Y-%m-%d")})'
        subtitle = 'اليوم'
    elif period == 'last_month':
        if today.month == 1:
            lm_year, lm_month = today.year - 1, 12
        else:
            lm_year, lm_month = today.year, today.month - 1
        _, num_days = calendar.monthrange(lm_year, lm_month)
        start_date = date(lm_year, lm_month, 1)
        end_date = date(lm_year, lm_month, num_days)
        title = f'الشهر السابق ({ARABIC_MONTHS[lm_month]} {lm_year})'
        subtitle = 'الشهر السابق'
    else:  # this_month (default)
        period = 'this_month'
        _, num_days = calendar.monthrange(today.year, today.month)
        start_date = date(today.year, today.month, 1)
        end_date = date(today.year, today.month, num_days)
        title = f'الشهر الحالي ({ARABIC_MONTHS[today.month]} {today.year})'
        subtitle = 'الشهر الحالي'

    return {
        'period': period,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'title': title,
        'subtitle': subtitle,
        'is_today': (period == 'today'),
        'is_this_month': (period == 'this_month'),
        'is_last_month': (period == 'last_month'),
    }


def _build_production_groups(entries):
    """
    Group production entries into nested structure:
    { model_code: { 'color/size': { stage_name: qty } } }
    Also returns model display name mapping.
    """
    groups = {}
    model_names = {}
    for e in entries:
        model_code = e.variant.product_model.code
        model_names[model_code] = e.variant.product_model.name
        size_key = f"{e.variant.color.name} / {e.variant.size.name}"
        stage_name = e.stage.name
        groups.setdefault(model_code, {}).setdefault(size_key, {})
        groups[model_code][size_key][stage_name] = (
            groups[model_code][size_key].get(stage_name, 0) + e.quantity
        )
    return groups, model_names


class ExternalWorkerDashboardView(View):
    """
    Worker-only dashboard accessible via Telegram magic-link.
    Shows production data strictly for Today, This Month, or Last Month.
    """
    template_name = 'external/worker_dashboard.html'

    def get(self, request):
        worker, error_redirect = _require_worker_session(request)
        if error_redirect:
            return error_redirect

        # Period filtering: today, this_month, last_month
        period_param = request.GET.get('period')
        if not period_param:
            if request.GET.get('year') or request.GET.get('month'):
                try:
                    y = int(request.GET.get('year'))
                    m = int(request.GET.get('month'))
                    today = date.today()
                    if y == today.year and m == today.month:
                        period_param = 'this_month'
                    else:
                        period_param = 'last_month'
                except (ValueError, TypeError):
                    period_param = 'this_month'
            else:
                period_param = 'this_month'

        period_ctx = get_worker_period_context(period_param)
        start_date = period_ctx['start_date']
        end_date = period_ctx['end_date']

        summary = get_worker_earnings(worker, start_date, end_date)
        history = list(
            get_worker_production_history(worker, start_date, end_date)
            .select_related('variant__product_model', 'variant__color', 'variant__size', 'stage')
        )

        # Build grouped display
        production_groups, model_names = _build_production_groups(history)

        if request.GET.get('export') == 'pdf':
            variant_breakdown = get_worker_variant_breakdown(worker, start_date, end_date)

            pdf = FactoryPDFReport(
                title=f'كشف إنتاج ومستحقات العامل: {worker.name}',
                subtitle=f'الفترة من {start_date} إلى {end_date}'
            )
            base_url = request.build_absolute_uri('/')
            stage_names = "، ".join([s.name for s in worker.stages.all()]) or 'غير مسند'
            pdf.add_header(filters_dict={
                'العامل': worker.name,
                'المراحل المسندة': stage_names,
                'الفترة': f'{start_date} إلى {end_date}',
            })
            pdf.add_kpis([
                ('إجمالي القطع المنتجة', f"{summary['total_qty']:,} قطعة"),
                ('إجمالي الأرباح والمستحقات', f"{summary['total_amount']:,.2f} ج.م"),
                ('عدد السجلات المسجلة', f"{summary['entry_count']:,} سجل"),
            ])

            if variant_breakdown:
                pdf.add_section_title('ملخص الإنتاج المجمع حسب الموديل والمرحلة (مرتب)')
                vb_rows = []
                for vb in variant_breakdown:
                    vb_rows.append([
                        vb['variant__product_model__code'],
                        f"{vb['variant__color__name']} / {vb['variant__size__name']}",
                        vb['stage__name'],
                        f"{vb['total_quantity']:,}",
                        f"{vb['unit_price_snapshot']:.2f} ج.م",
                        f"{vb['total_earnings']:,.2f} ج.م",
                    ])
                pdf.add_table(
                    headers=['الموديل', 'النوع (لون/مقاس)', 'المرحلة', 'الكمية', 'سعر الوحدة', 'إجمالي المستحق'],
                    rows=vb_rows,
                    col_widths=[75, 120, 95, 65, 75, 85],
                    right_align_cols=[1, 2]
                )

            if history:
                pdf.add_section_title('سجل العمليات والإنتاج التفصيلي (مرتب حسب التاريخ الأحدث)')
                h_rows = []
                for e in history:
                    v_qr = generate_qr_image_flowable(build_variant_entry_url(e.variant, base_url), size=26)
                    h_rows.append([
                        str(e.production_date),
                        e.variant.product_model.code,
                        f"{e.variant.color.name} / {e.variant.size.name}",
                        e.stage.name,
                        f"{e.quantity:,}",
                        f"{e.total_amount:,.2f} ج.م",
                        v_qr,
                    ])
                pdf.add_table(
                    headers=['التاريخ', 'الموديل', 'النوع', 'المرحلة', 'الكمية', 'الأرباح', 'رمز QR'],
                    rows=h_rows,
                    col_widths=[65, 65, 115, 100, 55, 70, 65],
                    right_align_cols=[1, 2, 3]
                )

            return pdf.build_response(f'worker_statement_{start_date}_{end_date}.pdf')

        # Pagination for the raw history list
        paginator = Paginator(history, 20)
        page = paginator.get_page(request.GET.get('page'))

        return render(request, self.template_name, {
            'worker': worker,
            'summary': summary,
            'page_obj': page,
            'production_groups': production_groups,
            'model_names': model_names,
            'period_ctx': period_ctx,
            'start_date': start_date,
            'end_date': end_date,
        })


class ExternalLogoutView(View):
    def get(self, request):
        request.session.pop(EXTERNAL_SESSION_KEY, None)
        messages.success(request, 'تم تسجيل خروجك بنجاح.')
        return redirect('accounts:login')
