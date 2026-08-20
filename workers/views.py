from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.db.models import Q, Sum
from django.core.paginator import Paginator

from .models import Worker
from .forms import WorkerForm
from .services import get_worker_earnings, get_worker_production_history
from catalog.models import ProductionStage, Client
from catalog.services import build_variant_entry_url

from core.pdf import FactoryPDFReport, generate_qr_image_flowable
from core.utils import get_current_month_date_range


@method_decorator(login_required, name='dispatch')
class WorkerListView(View):
    def get(self, request):
        q = request.GET.get('q', '')
        stage_id = request.GET.get('stage', '')
        status = request.GET.get('status', '')
        workers = Worker.objects.prefetch_related('stages')
        if q:
            workers = workers.filter(Q(name__icontains=q) | Q(phone__icontains=q))
        if stage_id:
            workers = workers.filter(stages__id=stage_id)
        if status == 'active':
            workers = workers.filter(is_active=True)
        elif status == 'inactive':
            workers = workers.filter(is_active=False)

        stages = ProductionStage.objects.filter(is_active=True)

        if request.GET.get('export') == 'pdf':
            pdf = FactoryPDFReport(
                title='دليل وسجل العمال والمراحل المسندة',
                subtitle='بيانات العمال وتوزيع مراحل الإنتاج'
            )
            stage_name = 'الكل'
            if stage_id:
                st = stages.filter(pk=stage_id).first()
                if st:
                    stage_name = st.name

            status_text = 'الكل' if not status else ('النشطين فقط' if status == 'active' else 'غير النشطين')
            pdf.add_header(filters_dict={
                'بحث': q if q else 'الكل',
                'المرحلة': stage_name,
                'الحالة': status_text,
            })
            total_workers = workers.count()
            active_workers = workers.filter(is_active=True).count()
            pdf.add_kpis([
                ('إجمالي العمال', f"{total_workers:,} عامل"),
                ('العمال النشطون', f"{active_workers:,} عامل"),
            ])

            table_rows = []
            for w in workers.order_by('name'):
                stage_names = "، ".join([s.name for s in w.stages.all()]) or 'غير مسند'
                table_rows.append([
                    w.name,
                    w.phone or '—',
                    stage_names,
                    'نشط' if w.is_active else 'معطل',
                ])
            pdf.add_table(
                headers=['اسم العامل', 'رقم الهاتف', 'المراحل المسندة', 'الحالة'],
                rows=table_rows,
                col_widths=[160, 115, 185, 75],
                right_align_cols=[0, 2]
            )
            return pdf.build_response('workers_list.pdf')

        paginator = Paginator(workers, 20)
        page = paginator.get_page(request.GET.get('page'))
        all_workers = Worker.objects.prefetch_related('stages')
        if q:
            all_workers = all_workers.filter(Q(name__icontains=q) | Q(phone__icontains=q))
        if stage_id:
            all_workers = all_workers.filter(stages__id=stage_id)
        return render(request, 'workers/list.html', {
            'page_obj': page, 'q': q, 'stages': stages, 'stage_id': stage_id, 'status': status,
            'active_workers': all_workers.filter(is_active=True),
            'inactive_workers': all_workers.filter(is_active=False),
        })


@method_decorator(login_required, name='dispatch')
class WorkerCreateView(View):
    def get(self, request):
        return render(request, 'workers/form.html', {'form': WorkerForm(), 'title': 'إضافة عامل جديد'})

    def post(self, request):
        form = WorkerForm(request.POST)
        if form.is_valid():
            worker = form.save()
            messages.success(request, f'تم إضافة العامل "{worker.name}" بنجاح.')
            return redirect('workers:detail', pk=worker.pk)
        return render(request, 'workers/form.html', {'form': form, 'title': 'إضافة عامل جديد'})


@method_decorator(login_required, name='dispatch')
class WorkerEditView(View):
    def get(self, request, pk):
        worker = get_object_or_404(Worker, pk=pk)
        return render(request, 'workers/form.html', {
            'form': WorkerForm(instance=worker),
            'worker': worker,
            'title': f'تعديل: {worker.name}'
        })

    def post(self, request, pk):
        worker = get_object_or_404(Worker, pk=pk)
        form = WorkerForm(request.POST, instance=worker)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث بيانات العامل بنجاح.')
            return redirect('workers:detail', pk=worker.pk)
        return render(request, 'workers/form.html', {
            'form': form, 'worker': worker, 'title': f'تعديل: {worker.name}'
        })


import calendar
from datetime import date
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from notifications.models import MagicLoginToken
from .services import get_worker_earnings, get_worker_production_history, get_worker_variant_breakdown

ARABIC_MONTHS = [
    '', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
    'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
]


def get_month_navigation_context(year=None, month=None):
    today = date.today()
    try:
        y = int(year) if year else today.year
        m = int(month) if month else today.month
    except (ValueError, TypeError):
        y, m = today.year, today.month

    if m < 1 or m > 12:
        m = today.month

    _, num_days = calendar.monthrange(y, m)
    start_date = date(y, m, 1)
    end_date = date(y, m, num_days)

    if m == 1:
        prev_year, prev_month = y - 1, 12
    else:
        prev_year, prev_month = y, m - 1

    if m == 12:
        next_year, next_month = y + 1, 1
    else:
        next_year, next_month = y, m + 1

    if today.month == 1:
        last_month_year, last_month_month = today.year - 1, 12
    else:
        last_month_year, last_month_month = today.year, today.month - 1

    return {
        'selected_year': y,
        'selected_month': m,
        'month_name': ARABIC_MONTHS[m],
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'prev_year': prev_year,
        'prev_month': prev_month,
        'next_year': next_year,
        'next_month': next_month,
        'this_year': today.year,
        'this_month': today.month,
        'last_month_year': last_month_year,
        'last_month_month': last_month_month,
        'is_current_month': (y == today.year and m == today.month),
        'is_last_month': (y == last_month_year and m == last_month_month),
    }


@method_decorator(login_required, name='dispatch')
class WorkerDetailView(View):
    def get(self, request, pk):
        worker = get_object_or_404(Worker.objects.prefetch_related('stages'), pk=pk)

        # Month Navigation
        req_year = request.GET.get('year')
        req_month = request.GET.get('month')
        month_ctx = get_month_navigation_context(req_year, req_month)

        start_date = request.GET.get('start_date') or month_ctx['start_date']
        end_date = request.GET.get('end_date') or month_ctx['end_date']
        stage_id = request.GET.get('stage') or None

        summary = get_worker_earnings(worker, start_date, end_date, stage_id)
        history = get_worker_production_history(worker, start_date, end_date, stage_id)
        variant_breakdown = get_worker_variant_breakdown(worker, start_date, end_date)

        stages = ProductionStage.objects.filter(is_active=True)

        if request.GET.get('export') == 'pdf':
            pdf = FactoryPDFReport(
                title=f'كشف إنتاج ومستحقات العامل: {worker.name}',
                subtitle=f'الفترة من {start_date} إلى {end_date}'
            )
            stage_names = "، ".join([s.name for s in worker.stages.all()]) or 'غير مسند'
            pdf.add_header(filters_dict={
                'العامل': worker.name,
                'رقم الهاتف': worker.phone or '—',
                'المراحل المسندة': stage_names,
                'الفترة': f'{start_date} إلى {end_date}',
            })
            pdf.add_kpis([
                ('إجمالي القطع المنتجة', f"{summary['total_qty']:,} قطعة"),
                ('إجمالي المستحقات والأرباح', f"{summary['total_amount']:,.2f} ج.م"),
                ('عدد سجلات الإنتاج', f"{summary['entry_count']:,} سجل"),
            ])

            if variant_breakdown:
                pdf.add_section_title('ملخص الإنتاج حسب نوع الصنف والمرحلة')
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
                pdf.add_section_title('سجل العمليات والإنتاج المفصل')
                h_rows = []
                base_url = request.build_absolute_uri('/')
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
                    col_widths=[65, 75, 95, 90, 55, 70, 85],
                    right_align_cols=[1, 2, 3]
                )

            return pdf.build_response(f'worker_{worker.pk}_statement_{start_date}_{end_date}.pdf')

        paginator = Paginator(history, 25)
        page = paginator.get_page(request.GET.get('page'))

        # Generate telegram bot deep link for instant binding
        telegram_bot_deep_link = f"https://t.me/Testing_Factory_Bot?start=w_{worker.pk}"

        # Generate single-use telegram login token (1 hour validity)
        token_obj = MagicLoginToken.create_token('worker', worker.pk, worker.name, expiry_minutes=60)
        telegram_direct_url = request.build_absolute_uri(
            reverse('workers:telegram_direct_login', kwargs={'token': token_obj.token})
        )

        return render(request, 'workers/detail.html', {
            'worker': worker,
            'summary': summary,
            'variant_breakdown': variant_breakdown,
            'page_obj': page,
            'stages': stages,
            'month_ctx': month_ctx,
            'start_date': start_date,
            'end_date': end_date,
            'stage_id': stage_id,
            'telegram_direct_url': telegram_direct_url,
            'telegram_bot_deep_link': telegram_bot_deep_link,
        })


@method_decorator(login_required, name='dispatch')
class GenerateWorkerTelegramLinkView(View):
    """Generate on-demand 1-hour telegram link and deep-link for the worker."""
    def get(self, request, pk):
        worker = get_object_or_404(Worker, pk=pk)
        token_obj = MagicLoginToken.create_token('worker', worker.pk, worker.name, expiry_minutes=60)
        login_url = request.build_absolute_uri(
            reverse('workers:telegram_direct_login', kwargs={'token': token_obj.token})
        )
        deep_link = f"https://t.me/Testing_Factory_Bot?start=w_{worker.pk}"
        return JsonResponse({
            'status': 'ok',
            'worker_id': worker.pk,
            'worker_name': worker.name,
            'login_url': login_url,
            'deep_link': deep_link,
            'expires_in_hours': 1,
            'is_single_use': False,
        })


class WorkerTelegramDirectLoginView(View):
    """
    Validates a single-use 1-hour direct login URL from Telegram and logs the worker
    into their external production portal.
    Ensures link can only be used once.
    """
    def get(self, request, token):
        try:
            token_obj = MagicLoginToken.objects.get(token=token, entity_type='worker')
        except MagicLoginToken.DoesNotExist:
            messages.error(request, 'رابط الدخول غير صالح أو انتهت صلاحيته.')
            return redirect('accounts:login')

        if not token_obj.is_valid:
            messages.error(request, 'عذراً، هذا الرابط مستخدم بالفعل أو انتهت صلاحيته (صلاحية الرابط للاستخدام مرة واحدة فقط وخلال ساعة واحدة).')
            return redirect('accounts:login')

        # Enforce single-use: mark token as used immediately
        token_obj.is_used = True
        token_obj.save()

        try:
            worker = Worker.objects.get(pk=token_obj.entity_id, is_active=True)
        except Worker.DoesNotExist:
            messages.error(request, 'حساب العامل غير نشط أو غير موجود.')
            return redirect('accounts:login')

        from external.views import EXTERNAL_SESSION_KEY
        request.session[EXTERNAL_SESSION_KEY] = {
            'type': 'worker',
            'entity_id': worker.pk,
            'name': worker.name,
            'authenticated_at': timezone.now().isoformat(),
            'source': 'telegram_single_use_token',
        }
        request.session.set_expiry(3600)  # 1 hour session
        messages.success(request, f'أهلاً بك يا {worker.name}! تم تسجيل دخولك بنجاح.')
        next_url = request.GET.get('next')
        if next_url and next_url.startswith('/'):
            return redirect(next_url)
        return redirect('external:worker_dashboard')



@login_required
def worker_toggle(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    worker.is_active = not worker.is_active
    worker.save()
    messages.success(request, f'تم {"تفعيل" if worker.is_active else "تعطيل"} العامل.')
    return redirect('workers:detail', pk=pk)

