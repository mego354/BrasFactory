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
            {'url': '/reports/by-model/', 'icon': '📦', 'title': 'تقرير الموديلات', 'subtitle': 'إنتاج مجمع حسب الموديل'},
            {'url': '/reports/by-worker/', 'icon': '👷', 'title': 'تقرير العمال', 'subtitle': 'أرباح وإنتاج كل عامل'},
            {'url': '/reports/by-client/', 'icon': '👥', 'title': 'تقرير العملاء', 'subtitle': 'قيمة الإنتاج لكل عميل'},
            {'url': '/reports/by-stage/', 'icon': '⚙️', 'title': 'تقرير المراحل', 'subtitle': 'إنتاج وتكلفة كل مرحلة'},
        ]
        return render(request, 'reports/index.html', {'reports': reports})


@method_decorator(login_required, name='dispatch')
class ReportByModelView(View):
    def get(self, request):
        filters = get_filters(request)
        data = services.production_by_model(filters)
        summary = services.overall_summary(filters)
        clients = Client.objects.filter(is_active=True)

        if request.GET.get('export') == 'pdf':
            client_name = 'كل العملاء'
            if filters['client_id']:
                cl = clients.filter(pk=filters['client_id']).first()
                if cl:
                    client_name = cl.name

            pdf = FactoryPDFReport(
                title='تقرير الإنتاج المجمع حسب الموديل وأكواد QR للتسجيل',
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
                ('عدد سجلات الإنتاج', f"{summary['entry_count']:,} سجل"),
            ])

            table_rows = []
            for r in data:
                m_id = r.get('variant__product_model__id')
                c_id = r.get('variant__product_model__client_id')
                register_url = f"{entry_base_url}?client={c_id}&model={m_id}" if (c_id and m_id) else entry_base_url
                qr_flowable = generate_qr_image_flowable(register_url, size=32)

                table_rows.append([
                    r['variant__product_model__code'],
                    r['variant__product_model__name'],
                    f"{r['total_qty']:,}",
                    f"{r['total_value']:,.2f} ج.م",
                    qr_flowable,
                ])

            pdf.add_table(
                headers=['نوع الموديل', 'اسم الموديل', 'الكمية', 'القيمة', 'رمز QR للتسجيل'],
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
        data = services.production_by_worker(filters)
        summary = services.overall_summary(filters)
        stages = ProductionStage.objects.filter(is_active=True)

        if request.GET.get('export') == 'pdf':
            stage_name = 'كل المراحل'
            if filters['stage_id']:
                st = stages.filter(pk=filters['stage_id']).first()
                if st:
                    stage_name = st.name

            pdf = FactoryPDFReport(
                title='تقرير إنتاج ومستحقات العمال',
                subtitle=f"الفترة من {filters['start_date']} إلى {filters['end_date']}"
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
            for r in data:
                table_rows.append([
                    r['worker__name'],
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
            return pdf.build_response('report_by_worker.pdf')

        return render(request, 'reports/by_worker.html', {
            'data': data, 'summary': summary, 'filters': filters, 'stages': stages
        })


@method_decorator(login_required, name='dispatch')
class ReportByClientView(View):
    def get(self, request):
        req_year = request.GET.get('year')
        req_month = request.GET.get('month')
        month_ctx = None
        if req_year or req_month or not (request.GET.get('start_date') or request.GET.get('end_date')):
            from core.utils import get_month_navigation_context
            month_ctx = get_month_navigation_context(req_year, req_month)

        filters = get_filters(request)
        if month_ctx and not request.GET.get('start_date'):
            filters['start_date'] = month_ctx['start_date']
        if month_ctx and not request.GET.get('end_date'):
            filters['end_date'] = month_ctx['end_date']

        data = services.production_by_client(filters)
        summary = services.overall_summary(filters)
        clients = Client.objects.filter(is_active=True).order_by('name')

        if request.GET.get('export') == 'pdf':
            pdf = FactoryPDFReport(
                title='تقرير إنتاج ومبيعات العملاء',
                subtitle=f"الفترة من {filters['start_date']} إلى {filters['end_date']}"
            )
            client_name = 'كل العملاء'
            if filters['client_id']:
                cl = clients.filter(pk=filters['client_id']).first()
                if cl:
                    client_name = cl.name

            pdf.add_header(filters_dict={
                'الفترة': f"{filters['start_date']} إلى {filters['end_date']}",
                'العميل': client_name,
            })
            pdf.add_kpis([
                ('إجمالي القطع المنتجة', f"{summary['total_qty']:,} قطعة"),
                ('إجمالي القيمة المحققة', f"{summary['total_value']:,.2f} ج.م"),
                ('عدد العملاء المنتجين', f"{len(data):,} عميل"),
                ('عدد سجلات الإنتاج', f"{summary['entry_count']:,} سجل"),
            ])

            table_rows = []
            for r in data:
                table_rows.append([
                    r['variant__product_model__client__code'],
                    r['variant__product_model__client__name'],
                    f"{r['total_qty']:,}",
                    f"{r['total_value']:,.2f} ج.م",
                    f"{r['model_count']} موديل",
                ])

            pdf.add_table(
                headers=['كود العميل', 'اسم العميل / الشركة', 'الكمية المنتجة', 'إجمالي القيمة', 'الموديلات'],
                rows=table_rows,
                col_widths=[85, 170, 95, 110, 75],
                right_align_cols=[1]
            )
            return pdf.build_response(f"report_by_client_{filters['start_date']}_{filters['end_date']}.pdf")

        return render(request, 'reports/by_client.html', {
            'data': data,
            'summary': summary,
            'filters': filters,
            'clients': clients,
            'month_ctx': month_ctx,
        })



@method_decorator(login_required, name='dispatch')
class ReportByStageView(View):
    def get(self, request):
        filters = get_filters(request)
        data = services.production_by_stage(filters)
        summary = services.overall_summary(filters)

        if request.GET.get('export') == 'pdf':
            pdf = FactoryPDFReport(
                title='تقرير تكلفة وإنتاج مراحل التشغيل',
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
