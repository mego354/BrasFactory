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


from core.pdf import FactoryPDFReport
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
        return render(request, 'workers/list.html', {
            'page_obj': page, 'q': q, 'stages': stages, 'stage_id': stage_id, 'status': status
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


@method_decorator(login_required, name='dispatch')
class WorkerDetailView(View):
    def get(self, request, pk):
        worker = get_object_or_404(Worker.objects.prefetch_related('stages'), pk=pk)
        start_date, end_date = get_current_month_date_range(
            request.GET.get('start_date'),
            request.GET.get('end_date')
        )
        stage_id = request.GET.get('stage') or None
        client_id = request.GET.get('client') or None

        summary = get_worker_earnings(worker, start_date, end_date, stage_id, client_id)
        history = get_worker_production_history(worker, start_date, end_date)

        stages = ProductionStage.objects.filter(is_active=True)
        clients = Client.objects.filter(is_active=True)

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

            if history:
                pdf.add_section_title('سجل العمليات والإنتاج المفصل')
                h_rows = []
                for e in history:
                    h_rows.append([
                        str(e.production_date),
                        e.variant.product_model.client.name,
                        e.variant.product_model.code,
                        f"{e.variant.color.name} / {e.variant.size.name}",
                        e.stage.name,
                        f"{e.quantity:,}",
                        f"{e.total_amount:,.2f} ج.م",
                    ])
                pdf.add_table(
                    headers=['التاريخ', 'العميل', 'الموديل', 'النوع', 'المرحلة', 'الكمية', 'الأرباح'],
                    rows=h_rows,
                    col_widths=[65, 85, 65, 95, 95, 55, 75],
                    right_align_cols=[1, 2, 3, 4]
                )

            return pdf.build_response(f'worker_{worker.pk}_statement_{start_date}_{end_date}.pdf')

        paginator = Paginator(history, 25)
        page = paginator.get_page(request.GET.get('page'))

        return render(request, 'workers/detail.html', {
            'worker': worker,
            'summary': summary,
            'page_obj': page,
            'stages': stages,
            'clients': clients,
            'start_date': start_date,
            'end_date': end_date,
            'stage_id': stage_id,
            'client_id': client_id,
        })


@login_required
def worker_toggle(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    worker.is_active = not worker.is_active
    worker.save()
    messages.success(request, f'تم {"تفعيل" if worker.is_active else "تعطيل"} العامل.')
    return redirect('workers:detail', pk=pk)
