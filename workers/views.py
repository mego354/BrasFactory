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
        paginator = Paginator(workers, 20)
        page = paginator.get_page(request.GET.get('page'))
        stages = ProductionStage.objects.filter(is_active=True)
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
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        stage_id = request.GET.get('stage') or None
        client_id = request.GET.get('client') or None

        summary = get_worker_earnings(worker, start_date, end_date, stage_id, client_id)
        history = get_worker_production_history(worker, start_date, end_date)
        paginator = Paginator(history, 25)
        page = paginator.get_page(request.GET.get('page'))

        stages = ProductionStage.objects.filter(is_active=True)
        clients = Client.objects.filter(is_active=True)

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
