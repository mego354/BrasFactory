import csv
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.http import HttpResponse

from catalog.models import Client, ProductModel, ProductionStage
from workers.models import Worker
from . import services


def get_filters(request):
    return {
        'start_date': request.GET.get('start_date', ''),
        'end_date': request.GET.get('end_date', ''),
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
        if request.GET.get('export') == 'csv':
            return _csv_response(
                data,
                ['كود الموديل', 'اسم الموديل', 'العميل', 'الكمية', 'القيمة'],
                lambda r: [
                    r['variant__product_model__code'],
                    r['variant__product_model__name'],
                    r['variant__product_model__client__name'],
                    r['total_qty'],
                    r['total_value'],
                ],
                'report_by_model'
            )
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
        if request.GET.get('export') == 'csv':
            return _csv_response(
                data,
                ['العامل', 'الكمية', 'الأرباح', 'عدد السجلات'],
                lambda r: [r['worker__name'], r['total_qty'], r['total_earnings'], r['entry_count']],
                'report_by_worker'
            )
        return render(request, 'reports/by_worker.html', {
            'data': data, 'summary': summary, 'filters': filters, 'stages': stages
        })


@method_decorator(login_required, name='dispatch')
class ReportByClientView(View):
    def get(self, request):
        filters = get_filters(request)
        data = services.production_by_client(filters)
        summary = services.overall_summary(filters)
        if request.GET.get('export') == 'csv':
            return _csv_response(
                data,
                ['كود العميل', 'اسم العميل', 'الكمية', 'القيمة', 'عدد الموديلات'],
                lambda r: [
                    r['variant__product_model__client__code'],
                    r['variant__product_model__client__name'],
                    r['total_qty'], r['total_value'], r['model_count']
                ],
                'report_by_client'
            )
        return render(request, 'reports/by_client.html', {
            'data': data, 'summary': summary, 'filters': filters
        })


@method_decorator(login_required, name='dispatch')
class ReportByStageView(View):
    def get(self, request):
        filters = get_filters(request)
        data = services.production_by_stage(filters)
        summary = services.overall_summary(filters)
        if request.GET.get('export') == 'csv':
            return _csv_response(
                data,
                ['المرحلة', 'الكمية', 'التكلفة', 'عدد العمال'],
                lambda r: [r['stage__name'], r['total_qty'], r['total_cost'], r['worker_count']],
                'report_by_stage'
            )
        return render(request, 'reports/by_stage.html', {
            'data': data, 'summary': summary, 'filters': filters
        })


def _csv_response(data, headers, row_fn, filename):
    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = f'attachment; filename="{filename}.csv"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for row in data:
        writer.writerow(row_fn(row))
    return response
