from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View

from catalog.models import Client, ProductModel, ProductionStage
from catalog.services import build_model_entry_url, build_variant_entry_url
from workers.models import Worker
from core.utils import get_current_month_date_range
from core.pdf import FactoryPDFReport, generate_qr_image_flowable
from django.urls import reverse
from . import services


def get_filters(request):
    start_date, end_date = get_current_month_date_range(
        request.GET.get('start_date'),
        request.GET.get('end_date')
    )
    return {
        'start_date': start_date,
        'end_date': end_date,
        'client_id': request.GET.get('client', '') or None,
        'model_id': request.GET.get('model', '') or None,
        'stage_id': request.GET.get('stage', '') or None,
        'worker_id': request.GET.get('worker', '') or None,
    }


@method_decorator(login_required, name='dispatch')
class ReportIndexView(View):
    def get(self, request):
        reports = [
            {'url': '/reports/by-worker/', 'icon': '👷', 'title': 'حسابات العمال (Worker Accounting)', 'subtitle': 'كشوف حسابات ومستحقات وإنتاج العمال'},
            {'url': '/reports/by-model/', 'icon': '📦', 'title': 'تقرير الموديلات', 'subtitle': 'إنتاج مجمع حسب الموديل'},
            {'url': '/reports/by-client/', 'icon': '👥', 'title': 'تقرير العملاء', 'subtitle': 'قيمة الإنتاج لكل عميل'},
            {'url': '/reports/by-stage/', 'icon': '⚙️', 'title': 'تقرير المراحل', 'subtitle': 'إنتاج وتكلفة كل مرحلة'},
        ]
        return render(request, 'reports/index.html', {'reports': reports})


@method_decorator(login_required, name='dispatch')
class ReportByModelView(View):
    def get(self, request):
        filters = get_filters(request)
        data = list(services.production_by_model(filters))
        # Sort by total quantity descending
        data.sort(key=lambda x: x.get('total_qty', 0), reverse=True)
        summary = services.overall_summary(filters)
        clients = Client.objects.filter(is_active=True)

        if request.GET.get('export') == 'pdf':
            client_name = 'كل العملاء'
            if filters['client_id']:
                cl = clients.filter(pk=filters['client_id']).first()
                if cl:
                    client_name = cl.name

            pdf = FactoryPDFReport(
                title='تقرير الإنتاج المجمع حسب الموديل (مرتب حسب الكمية)',
                subtitle=f"الفترة من {filters['start_date']} إلى {filters['end_date']}"
            )
            base_url = request.build_absolute_uri('/')
            entry_base_url = request.build_absolute_uri(reverse('production:entry'))

            pdf.add_header(filters_dict={
                'الفترة': f"{filters['start_date']} إلى {filters['end_date']}",
                'العميل': client_name,
            })
            pdf.add_kpis([
                ('إجمالي الكمية المنتجة', f"{summary['total_qty']:,} قطعة"),
                ('إجمالي القيمة الإجمالية', f"{summary['total_value']:,.2f} ج.م"),
                ('عدد الموديلات النشطة', f"{len(data):,} موديل"),
            ])

            table_rows = []
            for r in data:
                m_id = r.get('variant__product_model__id')
                c_id = r.get('variant__product_model__client_id')
                register_url = f"{entry_base_url}?client={c_id}&model={m_id}" if (c_id and m_id) else entry_base_url
                qr_flowable = generate_qr_image_flowable(register_url, size=30)

                table_rows.append([
                    r['variant__product_model__code'],
                    r['variant__product_model__name'],
                    f"{r['total_qty']:,}",
                    f"{r['total_value']:,.2f} ج.م",
                    qr_flowable,
                ])

            pdf.add_table(
                headers=['نوع الموديل', 'اسم الموديل', 'إجمالي الكمية', 'القيمة الإجمالية', 'رمز QR'],
                rows=table_rows,
                col_widths=[80, 195, 75, 90, 95],
                right_align_cols=[1]
            )
            return pdf.build_response('report_by_model.pdf')

        return render(request, 'reports/by_model.html', {
            'data': data, 'summary': summary, 'filters': filters, 'clients': clients
        })


@method_decorator(login_required, name='dispatch')
class ReportByWorkerView(View):
    def get(self, request):
        filters = get_filters(request)
        data = list(services.production_by_worker(filters))
        # Sort workers by total earnings descending (highest earners first)
        data.sort(key=lambda x: x.get('total_earnings', 0), reverse=True)
        summary = services.overall_summary(filters)
        stages = ProductionStage.objects.filter(is_active=True)

        if request.GET.get('export') == 'pdf':
            stage_name = 'كل المراحل'
            if filters['stage_id']:
                st = stages.filter(pk=filters['stage_id']).first()
                if st:
                    stage_name = st.name

            pdf = FactoryPDFReport(
                title='كشف حسابات ومستحقات العمال (Worker Accounting Report)',
                subtitle=f"الفترة من {filters['start_date']} إلى {filters['end_date']} — مرتب حسب إجمالي المستحقات"
            )
            pdf.add_header(filters_dict={
                'الفترة': f"{filters['start_date']} إلى {filters['end_date']}",
                'المرحلة': stage_name,
            })
            pdf.add_kpis([
                ('إجمالي القطع المنتجة', f"{summary['total_qty']:,} قطعة"),
                ('إجمالي المستحقات والأرباح', f"{summary['total_value']:,.2f} ج.م"),
                ('عدد العمال المنتجين', f"{len(data):,} عامل"),
            ])

            table_rows = []
            for rank, r in enumerate(data, 1):
                table_rows.append([
                    f"{rank}. {r['worker__name']}",
                    f"{r['total_qty']:,}",
                    f"{r['total_earnings']:,.2f} ج.م",
                    str(r['entry_count']),
                ])

            pdf.add_table(
                headers=['اسم العامل', 'الكمية المنتجة', 'إجمالي المستحقات', 'عدد السجلات'],
                rows=table_rows,
                col_widths=[205, 110, 120, 100],
                right_align_cols=[0]
            )
            return pdf.build_response('worker_accounting_report.pdf')

        return render(request, 'reports/by_worker.html', {
            'data': data, 'summary': summary, 'filters': filters, 'stages': stages
        })


@method_decorator(login_required, name='dispatch')
class ReportByClientView(View):
    def get(self, request):
        filters = get_filters(request)
        data = list(services.production_by_client(filters))
        # Sort clients by total value descending
        data.sort(key=lambda x: x.get('total_value', 0), reverse=True)
        summary = services.overall_summary(filters)

        if request.GET.get('export') == 'pdf':
            pdf = FactoryPDFReport(
                title='تقرير إنتاج ومبيعات العملاء (مرتب حسب القيمة)',
                subtitle=f"الفترة من {filters['start_date']} إلى {filters['end_date']}"
            )
            pdf.add_header(filters_dict={
                'الفترة': f"{filters['start_date']} إلى {filters['end_date']}",
            })
            pdf.add_kpis([
                ('إجمالي القطع المنتجة', f"{summary['total_qty']:,} قطعة"),
                ('إجمالي القيمة المحققة', f"{summary['total_value']:,.2f} ج.م"),
                ('عدد العملاء النشطين', f"{len(data):,} عميل"),
            ])

            table_rows = []
            for r in data:
                table_rows.append([
                    r['variant__product_model__client__code'],
                    f"{r['total_qty']:,}",
                    f"{r['total_value']:,.2f} ج.م",
                    str(r['model_count']),
                ])

            pdf.add_table(
                headers=['كود العميل', 'الكمية المنتجة', 'إجمالي القيمة', 'الموديلات'],
                rows=table_rows,
                col_widths=[100, 135, 130, 170],
                right_align_cols=[]
            )
            return pdf.build_response('report_by_client.pdf')

        return render(request, 'reports/by_client.html', {
            'data': data, 'summary': summary, 'filters': filters
        })


@method_decorator(login_required, name='dispatch')
class ReportByStageView(View):
    def get(self, request):
        filters = get_filters(request)
        data = list(services.production_by_stage(filters))
        # Sort stages by total quantity descending
        data.sort(key=lambda x: x.get('total_qty', 0), reverse=True)
        summary = services.overall_summary(filters)

        if request.GET.get('export') == 'pdf':
            pdf = FactoryPDFReport(
                title='تقرير تكلفة وإنتاج مراحل التشغيل (مرتب حسب الكمية)',
                subtitle=f"الفترة من {filters['start_date']} إلى {filters['end_date']}"
            )
            pdf.add_header(filters_dict={
                'الفترة': f"{filters['start_date']} إلى {filters['end_date']}",
            })
            pdf.add_kpis([
                ('إجمالي القطع المنجزة', f"{summary['total_qty']:,} قطعة"),
                ('إجمالي تكلفة التشغيل', f"{summary['total_value']:,.2f} ج.م"),
                ('عدد المراحل النشطة', f"{len(data):,} مرحلة"),
            ])

            table_rows = []
            for r in data:
                table_rows.append([
                    r['stage__name'],
                    f"{r['total_qty']:,}",
                    f"{r['total_cost']:,.2f} ج.م",
                    str(r['worker_count']),
                ])

            pdf.add_table(
                headers=['اسم مرحلة الإنتاج', 'الكمية المنجزة', 'إجمالي التكلفة', 'عدد العمال'],
                rows=table_rows,
                col_widths=[195, 115, 125, 100],
                right_align_cols=[0]
            )
            return pdf.build_response('report_by_stage.pdf')

        return render(request, 'reports/by_stage.html', {
            'data': data, 'summary': summary, 'filters': filters
        })
