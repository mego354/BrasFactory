"""
Catalog Views — CRUD for Colors, Sizes, Stages, Clients, ProductModels, Variants
Includes 4-step model creation wizard.
"""
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views import View
from django.db.models import Q, Sum, Count
from django.http import JsonResponse
from django.core.paginator import Paginator

from core.mixins import LoginRequiredMixin
from .models import Color, Size, Client, ProductionStage, ProductModel, ProductModelStage, ProductVariant
from .forms import (
    ColorForm, SizeForm, ClientForm, ProductionStageForm,
    ModelStep1Form, ModelStep2Form, ModelStep3Form, ProductVariantPlanForm
)
from .services import (
    generate_variants, get_model_stage_price,
    build_model_entry_url, build_variant_entry_url, generate_qr_png_bytes, generate_qr_base64
)
from core.pdf import FactoryPDFReport, generate_qr_image_flowable
from django.http import HttpResponse


# ─────────────────────────────────────────────
# Settings Index
# ─────────────────────────────────────────────
@method_decorator(login_required, name='dispatch')
class SettingsIndexView(View):
    def get(self, request):
        return render(request, 'catalog/settings/index.html', {
            'colors': Color.objects.all()[:5],
            'sizes': Size.objects.all()[:5],
            'stages': ProductionStage.objects.all()[:5],
        })


# ─────────────────────────────────────────────
# Color CRUD
# ─────────────────────────────────────────────
@method_decorator(login_required, name='dispatch')
class ColorListView(View):
    def get(self, request):
        q = request.GET.get('q', '')
        colors = Color.objects.all()
        if q:
            colors = colors.filter(name__icontains=q)
        return render(request, 'catalog/settings/colors.html', {
            'colors': colors, 'q': q,
            'active_colors': colors.filter(is_active=True),
            'inactive_colors': colors.filter(is_active=False),
            'form': ColorForm(),
        })

    def post(self, request):
        form = ColorForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم إضافة اللون بنجاح.')
            return redirect('catalog:color_list')
        colors = Color.objects.all()
        return render(request, 'catalog/settings/colors.html', {
            'colors': colors, 'form': form,
            'active_colors': colors.filter(is_active=True),
            'inactive_colors': colors.filter(is_active=False),
        })


@method_decorator(login_required, name='dispatch')
class ColorEditView(View):
    def get(self, request, pk):
        color = get_object_or_404(Color, pk=pk)
        return render(request, 'catalog/settings/color_form.html', {
            'form': ColorForm(instance=color), 'color': color
        })

    def post(self, request, pk):
        color = get_object_or_404(Color, pk=pk)
        form = ColorForm(request.POST, instance=color)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث اللون بنجاح.')
            return redirect('catalog:color_list')
        return render(request, 'catalog/settings/color_form.html', {'form': form, 'color': color})


@login_required
def color_toggle(request, pk):
    color = get_object_or_404(Color, pk=pk)
    color.is_active = not color.is_active
    color.save()
    status = 'نشط' if color.is_active else 'غير نشط'
    messages.success(request, f'تم تغيير حالة اللون إلى: {status}')
    return redirect('catalog:color_list')


# ─────────────────────────────────────────────
# Size CRUD
# ─────────────────────────────────────────────
@method_decorator(login_required, name='dispatch')
class SizeListView(View):
    def get(self, request):
        sizes = Size.objects.all()
        return render(request, 'catalog/settings/sizes.html', {
            'sizes': sizes,
            'active_sizes': sizes.filter(is_active=True),
            'inactive_sizes': sizes.filter(is_active=False),
            'form': SizeForm()
        })

    def post(self, request):
        form = SizeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم إضافة المقاس بنجاح.')
            return redirect('catalog:size_list')
        sizes = Size.objects.all()
        return render(request, 'catalog/settings/sizes.html', {
            'sizes': sizes,
            'active_sizes': sizes.filter(is_active=True),
            'inactive_sizes': sizes.filter(is_active=False),
            'form': form,
        })


@login_required
def size_toggle(request, pk):
    size = get_object_or_404(Size, pk=pk)
    size.is_active = not size.is_active
    size.save()
    messages.success(request, f'تم تغيير حالة المقاس.')
    return redirect('catalog:size_list')


# ─────────────────────────────────────────────
# Production Stage CRUD
# ─────────────────────────────────────────────
@method_decorator(login_required, name='dispatch')
class StageListView(View):
    def get(self, request):
        stages = ProductionStage.objects.all()
        return render(request, 'catalog/settings/stages.html', {
            'stages': stages,
            'active_stages': stages.filter(is_active=True),
            'inactive_stages': stages.filter(is_active=False),
            'form': ProductionStageForm()
        })

    def post(self, request):
        form = ProductionStageForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم إضافة المرحلة بنجاح.')
            return redirect('catalog:stage_list')
        stages = ProductionStage.objects.all()
        return render(request, 'catalog/settings/stages.html', {
            'stages': stages,
            'active_stages': stages.filter(is_active=True),
            'inactive_stages': stages.filter(is_active=False),
            'form': form,
        })


@login_required
def stage_toggle(request, pk):
    stage = get_object_or_404(ProductionStage, pk=pk)
    stage.is_active = not stage.is_active
    stage.save()
    messages.success(request, 'تم تغيير حالة المرحلة.')
    return redirect('catalog:stage_list')


# ─────────────────────────────────────────────
# Client CRUD
# ─────────────────────────────────────────────
@method_decorator(login_required, name='dispatch')
class ClientListView(View):
    def get(self, request):
        q = request.GET.get('q', '')
        status = request.GET.get('status', '')
        clients = Client.objects.annotate(models_count=Count('product_models')).order_by('name')
        if q:
            clients = clients.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(phone__icontains=q))
        if status == 'active':
            clients = clients.filter(is_active=True)
        elif status == 'inactive':
            clients = clients.filter(is_active=False)

        if request.GET.get('export') == 'pdf':
            pdf = FactoryPDFReport(
                title='دليل وسجل العملاء',
                subtitle='قائمة العملاء المسجلين وبيانات الاتصال والموديلات'
            )
            status_text = 'الكل' if not status else ('النشطين فقط' if status == 'active' else 'غير النشطين')
            pdf.add_header(filters_dict={
                'بحث': q if q else 'الكل',
                'الحالة': status_text,
            })
            total_clients = clients.count()
            active_count = clients.filter(is_active=True).count()
            pdf.add_kpis([
                ('إجمالي العملاء', f"{total_clients:,} عميل"),
                ('العملاء النشطون', f"{active_count:,} عميل"),
            ])
            table_rows = []
            for cl in clients:
                table_rows.append([
                    cl.code,
                    cl.name,
                    cl.phone or '—',
                    str(cl.models_count),
                    'نشط' if cl.is_active else 'معطل',
                ])
            pdf.add_table(
                headers=['كود العميل', 'اسم العميل', 'رقم الهاتف', 'الموديلات', 'الحالة'],
                rows=table_rows,
                col_widths=[90, 195, 110, 70, 70],
                right_align_cols=[1]
            )
            return pdf.build_response('clients_list.pdf')

        paginator = Paginator(clients, 20)
        page = paginator.get_page(request.GET.get('page'))
        all_clients = Client.objects.annotate(models_count=Count('product_models')).order_by('name')
        if q:
            all_clients = all_clients.filter(Q(name__icontains=q) | Q(code__icontains=q) | Q(phone__icontains=q))
        return render(request, 'catalog/clients/list.html', {
            'page_obj': page, 'q': q, 'status': status,
            'active_clients': all_clients.filter(is_active=True),
            'inactive_clients': all_clients.filter(is_active=False),
        })


@method_decorator(login_required, name='dispatch')
class ClientCreateView(View):
    def get(self, request):
        return render(request, 'catalog/clients/form.html', {'form': ClientForm(), 'title': 'إضافة عميل جديد'})

    def post(self, request):
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(request, f'تم إضافة العميل "{client.name}" بنجاح.')
            return redirect('catalog:client_detail', pk=client.pk)
        return render(request, 'catalog/clients/form.html', {'form': form, 'title': 'إضافة عميل جديد'})


@method_decorator(login_required, name='dispatch')
class ClientEditView(View):
    def get(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        return render(request, 'catalog/clients/form.html', {
            'form': ClientForm(instance=client), 'client': client,
            'title': f'تعديل العميل: {client.name}'
        })

    def post(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(request, 'تم تحديث بيانات العميل بنجاح.')
            return redirect('catalog:client_detail', pk=client.pk)
        return render(request, 'catalog/clients/form.html', {
            'form': form, 'client': client, 'title': f'تعديل العميل: {client.name}'
        })


@method_decorator(login_required, name='dispatch')
class ClientDetailView(View):
    def get(self, request, pk):
        client = get_object_or_404(Client, pk=pk)
        models = client.product_models.select_related().prefetch_related('variants').order_by('-created_at')
        # Financial summary
        from production.models import ProductionEntry
        entries = ProductionEntry.objects.filter(
            variant__product_model__client=client,
            is_cancelled=False
        )
        total_value = entries.aggregate(total=Sum('total_amount'))['total'] or 0
        total_qty = entries.aggregate(total=Sum('quantity'))['total'] or 0

        if request.GET.get('export') == 'pdf':
            pdf = FactoryPDFReport(
                title=f'كشف حساب وبيانات العميل: {client.name}',
                subtitle=f'كود العميل: {client.code}'
            )
            pdf.add_header(filters_dict={
                'كود العميل': client.code,
                'رقم الهاتف': client.phone or '—',
                'الحالة': 'نشط' if client.is_active else 'معطل',
            })
            pdf.add_kpis([
                ('إجمالي القطع المنتجة', f"{total_qty:,} قطعة"),
                ('إجمالي قيمة الإنتاج', f"{total_value:,.2f} ج.م"),
                ('عدد الموديلات', f"{models.count():,} موديل"),
            ])

            base_url = request.build_absolute_uri('/')
            pdf.add_section_title('موديلات العميل والكميات المخططة وأكواد QR للتسجيل')
            model_rows = []
            for m in models:
                m_qr = generate_qr_image_flowable(build_model_entry_url(m, base_url), size=28)
                model_rows.append([
                    m.code,
                    m.name,
                    f"{m.variants.count()} نوع",
                    f"{m.total_planned:,} قطعة",
                    'نشط' if m.is_active else 'معطل',
                    m_qr,
                ])
            pdf.add_table(
                headers=['الكود', 'اسم الموديل', 'الأنواع', 'المخطط', 'الحالة', 'رمز QR'],
                rows=model_rows,
                col_widths=[75, 160, 80, 85, 65, 70],
                right_align_cols=[1]
            )

            # Recent production entries
            recent = entries.select_related('variant__color', 'variant__size', 'stage').order_by('-created_at')[:25]
            if recent:
                pdf.add_section_title('آخر سجلات الإنتاج للعميل مع أكواد QR للأنواع')
                recent_rows = []
                for e in recent:
                    v_qr = generate_qr_image_flowable(build_variant_entry_url(e.variant, base_url), size=26)
                    recent_rows.append([
                        str(e.production_date),
                        e.variant.product_model.code,
                        f"{e.variant.color.name} / {e.variant.size.name}",
                        e.stage.name,
                        f"{e.quantity:,}",
                        v_qr,
                    ])
                pdf.add_table(
                    headers=['التاريخ', 'الموديل', 'النوع', 'المرحلة', 'الكمية', 'رمز QR'],
                    rows=recent_rows,
                    col_widths=[75, 75, 140, 115, 65, 65],
                    right_align_cols=[2, 3]
                )
            return pdf.build_response(f'client_{client.code}_report.pdf')

        return render(request, 'catalog/clients/detail.html', {
            'client': client,
            'models': models,
            'total_value': total_value,
            'total_qty': total_qty,
        })


@login_required
def client_toggle(request, pk):
    client = get_object_or_404(Client, pk=pk)
    client.is_active = not client.is_active
    client.save()
    messages.success(request, f'تم {"تفعيل" if client.is_active else "تعطيل"} العميل.')
    return redirect('catalog:client_detail', pk=pk)


# ─────────────────────────────────────────────
# Product Model — Wizard (4 steps)
# ─────────────────────────────────────────────
SESSION_KEY = 'new_model_wizard'


@method_decorator(login_required, name='dispatch')
class ModelListView(View):
    def get(self, request):
        q = request.GET.get('q', '')
        client_id = request.GET.get('client', '')
        status = request.GET.get('status', '')
        models = ProductModel.objects.select_related('client').annotate(
            variants_count=Count('variants')
        )
        if q:
            models = models.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(client__name__icontains=q))
        if client_id:
            models = models.filter(client_id=client_id)
        if status == 'active':
            models = models.filter(is_active=True)
        elif status == 'inactive':
            models = models.filter(is_active=False)

        clients = Client.objects.filter(is_active=True)

        if request.GET.get('export') == 'pdf':
            pdf = FactoryPDFReport(
                title='دليل وسجل موديلات المنتجات',
                subtitle='بيانات الموديلات والعملاء والأنواع المسجلة'
            )
            client_name = 'الكل'
            if client_id:
                c_obj = clients.filter(pk=client_id).first()
                if c_obj:
                    client_name = c_obj.name

            status_text = 'الكل' if not status else ('النشطة فقط' if status == 'active' else 'غير النشطة')
            pdf.add_header(filters_dict={
                'بحث': q if q else 'الكل',
                'العميل': client_name,
                'الحالة': status_text,
            })
            total_models = models.count()
            active_models = models.filter(is_active=True).count()
            pdf.add_kpis([
                ('إجمالي الموديلات', f"{total_models:,} موديل"),
                ('الموديلات النشطة', f"{active_models:,} موديل"),
            ])
            table_rows = []
            base_url = request.build_absolute_uri('/')
            for m in models.order_by('-created_at'):
                register_url = build_model_entry_url(m, base_url)
                qr_flowable = generate_qr_image_flowable(register_url, size=30)
                table_rows.append([
                    m.code,
                    m.name,
                    m.client.name,
                    f"{m.variants_count} نوع",
                    f"{m.total_planned:,} قطعة",
                    'نشط' if m.is_active else 'معطل',
                    qr_flowable,
                ])
            pdf.add_table(
                headers=['الكود', 'اسم الموديل', 'العميل', 'الأنواع', 'المخطط', 'الحالة', 'رمز QR'],
                rows=table_rows,
                col_widths=[70, 130, 115, 55, 60, 50, 55],
                right_align_cols=[1, 2]
            )
            return pdf.build_response('models_list.pdf')

        paginator = Paginator(models.order_by('-created_at'), 20)
        page = paginator.get_page(request.GET.get('page'))
        return render(request, 'catalog/models/list.html', {
            'page_obj': page, 'q': q, 'client_id': client_id,
            'status': status, 'clients': clients,
        })


@method_decorator(login_required, name='dispatch')
class ModelWizardStep1(View):
    def get(self, request):
        request.session.pop(SESSION_KEY, None)
        return render(request, 'catalog/models/wizard_step1.html', {
            'form': ModelStep1Form(), 'step': 1
        })

    def post(self, request):
        form = ModelStep1Form(request.POST)
        if form.is_valid():
            data = {
                'code': form.cleaned_data['code'],
                'name': form.cleaned_data['name'],
                'client_id': form.cleaned_data['client'].pk,
                'description': form.cleaned_data['description'],
            }
            request.session[SESSION_KEY] = data
            return redirect('catalog:model_wizard_step2')
        return render(request, 'catalog/models/wizard_step1.html', {'form': form, 'step': 1})


@method_decorator(login_required, name='dispatch')
class ModelWizardStep2(View):
    def get(self, request):
        if SESSION_KEY not in request.session:
            return redirect('catalog:model_wizard_step1')
        return render(request, 'catalog/models/wizard_step2.html', {
            'form': ModelStep2Form(), 'step': 2,
            'wizard': request.session[SESSION_KEY],
            'colors': Color.objects.filter(is_active=True),
        })

    def post(self, request):
        form = ModelStep2Form(request.POST)
        if form.is_valid():
            wiz = request.session[SESSION_KEY]
            wiz['color_ids'] = [c.pk for c in form.cleaned_data['colors']]
            request.session[SESSION_KEY] = wiz
            return redirect('catalog:model_wizard_step3')
        return render(request, 'catalog/models/wizard_step2.html', {
            'form': form, 'step': 2,
            'colors': Color.objects.filter(is_active=True),
        })


@method_decorator(login_required, name='dispatch')
class ModelWizardStep3(View):
    def get(self, request):
        if SESSION_KEY not in request.session:
            return redirect('catalog:model_wizard_step1')
        return render(request, 'catalog/models/wizard_step3.html', {
            'form': ModelStep3Form(), 'step': 3,
            'wizard': request.session[SESSION_KEY],
            'sizes': Size.objects.filter(is_active=True).order_by('sort_order'),
        })

    def post(self, request):
        form = ModelStep3Form(request.POST)
        if form.is_valid():
            wiz = request.session[SESSION_KEY]
            wiz['size_ids'] = [s.pk for s in form.cleaned_data['sizes']]
            request.session[SESSION_KEY] = wiz
            return redirect('catalog:model_wizard_step_quantities')
        return render(request, 'catalog/models/wizard_step3.html', {
            'form': form, 'step': 3,
            'sizes': Size.objects.filter(is_active=True).order_by('sort_order'),
        })


@method_decorator(login_required, name='dispatch')
class ModelWizardStepQuantities(View):
    """New Step 3b: Enter planned quantity per color × size combination."""
    def get(self, request):
        if SESSION_KEY not in request.session:
            return redirect('catalog:model_wizard_step1')
        wiz = request.session[SESSION_KEY]
        colors = Color.objects.filter(pk__in=wiz.get('color_ids', []))
        sizes = Size.objects.filter(pk__in=wiz.get('size_ids', [])).order_by('sort_order')
        # Load previously saved quantities if going back
        saved_quantities = wiz.get('quantities', {})
        return render(request, 'catalog/models/wizard_step_quantities.html', {
            'colors': colors, 'sizes': sizes,
            'saved_quantities': saved_quantities,
            'wizard': wiz, 'step': '3b',
        })

    def post(self, request):
        wiz = request.session.get(SESSION_KEY)
        if not wiz:
            return redirect('catalog:model_wizard_step1')
        colors = Color.objects.filter(pk__in=wiz.get('color_ids', []))
        sizes = Size.objects.filter(pk__in=wiz.get('size_ids', [])).order_by('sort_order')
        quantities = {}
        for color in colors:
            for size in sizes:
                key = f"{color.pk}__{size.pk}"
                raw_val = request.POST.get(f'qty_{key}', '0').strip()
                try:
                    quantities[key] = max(0, int(raw_val))
                except (ValueError, TypeError):
                    quantities[key] = 0
        wiz['quantities'] = quantities
        request.session[SESSION_KEY] = wiz
        return redirect('catalog:model_wizard_step4')


@method_decorator(login_required, name='dispatch')
class ModelWizardStep4(View):
    """Stage selection + price entry."""
    def get(self, request):
        if SESSION_KEY not in request.session:
            return redirect('catalog:model_wizard_step1')
        stages = ProductionStage.objects.filter(is_active=True).order_by('sort_order')
        return render(request, 'catalog/models/wizard_step4.html', {
            'stages': stages, 'step': 4,
            'wizard': request.session[SESSION_KEY],
        })

    def post(self, request):
        stages = ProductionStage.objects.filter(is_active=True)
        stage_data = []
        has_selection = False
        errors = []

        for stage in stages:
            selected = request.POST.get(f'stage_{stage.pk}_selected') == 'on'
            price_raw = request.POST.get(f'stage_{stage.pk}_price', '').strip()
            if selected:
                has_selection = True
                # Normalize leading-dot format: .2 → 0.2
                if price_raw.startswith('.'):
                    price_raw = '0' + price_raw
                try:
                    price = float(price_raw)
                    if price < 0:
                        raise ValueError
                except ValueError:
                    errors.append(f'أدخل سعراً صحيحاً لمرحلة "{stage.name}".')
                    price = 0
                stage_data.append({
                    'stage_id': stage.pk,
                    'stage_name': stage.name,
                    'unit_price': price,
                    'sort_order': 0,
                })

        if not has_selection:
            errors.append('يجب اختيار مرحلة إنتاج واحدة على الأقل.')

        if errors:
            for err in errors:
                messages.error(request, err)
            stages = ProductionStage.objects.filter(is_active=True).order_by('sort_order')
            return render(request, 'catalog/models/wizard_step4.html', {
                'stages': stages, 'step': 4,
                'wizard': request.session.get(SESSION_KEY, {}),
            })

        wiz = request.session[SESSION_KEY]
        wiz['stages'] = stage_data
        request.session[SESSION_KEY] = wiz
        return redirect('catalog:model_wizard_review')


@method_decorator(login_required, name='dispatch')
class ModelWizardReview(View):
    """Step 6: Review before generation."""
    def get(self, request):
        wiz = request.session.get(SESSION_KEY)
        if not wiz:
            return redirect('catalog:model_wizard_step1')
        colors = Color.objects.filter(pk__in=wiz.get('color_ids', []))
        sizes = Size.objects.filter(pk__in=wiz.get('size_ids', [])).order_by('sort_order')
        client = Client.objects.get(pk=wiz['client_id'])
        variant_count = len(wiz.get('color_ids', [])) * len(wiz.get('size_ids', []))
        # Build quantities preview: {color_id: {size_id: qty}}
        raw_quantities = wiz.get('quantities', {})
        quantities_preview = {}
        for color in colors:
            for size in sizes:
                key = f"{color.pk}__{size.pk}"
                if key not in quantities_preview:
                    quantities_preview[key] = raw_quantities.get(key, 0)
        return render(request, 'catalog/models/wizard_review.html', {
            'wiz': wiz, 'colors': colors, 'sizes': sizes,
            'client': client, 'step': 6, 'variant_count': variant_count,
            'quantities_preview': raw_quantities,
        })


@method_decorator(login_required, name='dispatch')
class ModelWizardGenerate(View):
    """Step 6: Commit model + generate variants."""
    def post(self, request):
        from django.db import transaction
        wiz = request.session.get(SESSION_KEY)
        if not wiz:
            return redirect('catalog:model_wizard_step1')

        with transaction.atomic():
            model = ProductModel.objects.create(
                code=wiz['code'],
                name=wiz['name'],
                client_id=wiz['client_id'],
                description=wiz.get('description', ''),
            )
            model.colors.set(wiz['color_ids'])
            model.sizes.set(wiz['size_ids'])

            for i, sd in enumerate(wiz.get('stages', [])):
                ProductModelStage.objects.create(
                    product_model=model,
                    stage_id=sd['stage_id'],
                    unit_price=sd['unit_price'],
                    sort_order=sd.get('sort_order', i),
                )

            created, existing = generate_variants(model, quantities=wiz.get('quantities', {}))

        request.session.pop(SESSION_KEY, None)
        messages.success(
            request,
            f'تم إنشاء الموديل "{model.name}" بنجاح. تم توليد {created} نوع منتج.'
        )
        return redirect('catalog:model_detail', pk=model.pk)


@method_decorator(login_required, name='dispatch')
class ModelDetailView(View):
    def get(self, request, pk):
        model = get_object_or_404(
            ProductModel.objects.select_related('client').prefetch_related(
                'variants__color', 'variants__size',
                'model_stages__stage'
            ),
            pk=pk
        )
        from production.models import ProductionEntry
        from django.db.models import Sum

        # Stage summary: planned vs produced per stage
        stage_summaries = []
        total_planned = model.total_planned
        for ms in model.model_stages.filter(is_active=True).select_related('stage'):
            produced = ProductionEntry.objects.filter(
                variant__product_model=model,
                stage=ms.stage,
                is_cancelled=False
            ).aggregate(qty=Sum('quantity'))['qty'] or 0
            stage_summaries.append({
                'stage': ms.stage,
                'unit_price': ms.unit_price,
                'planned': total_planned,
                'produced': produced,
                'remaining': max(0, total_planned - produced),
                'pct': round((produced / total_planned * 100), 1) if total_planned > 0 else 0,
            })

        # Variants with QR codes
        base_url = request.build_absolute_uri('/')
        variants_data = []
        for v in model.variants.all().select_related('color', 'size'):
            entry_url = build_variant_entry_url(v, base_url)
            qr_b64 = generate_qr_base64(entry_url)
            variants_data.append({
                'variant': v,
                'entry_url': entry_url,
                'qr_b64': qr_b64,
            })

        # Recent production entries
        recent_entries = ProductionEntry.objects.filter(
            variant__product_model=model,
            is_cancelled=False
        ).select_related('variant__color', 'variant__size', 'stage', 'worker', 'created_by').order_by('-created_at')[:20]

        if request.GET.get('export') == 'pdf':
            pdf = FactoryPDFReport(
                title=f'بطاقة المواصفات ومتابعة إنتاج الموديل: {model.name}',
                subtitle=f'كود الموديل: {model.code} — العميل: {model.client.name}'
            )
            model_entry_url = build_model_entry_url(model, base_url)
            pdf.add_header(
                filters_dict={
                    'كود الموديل': model.code,
                    'العميل': model.client.name,
                    'الحالة': 'نشط' if model.is_active else 'معطل',
                },
                qr_data=model_entry_url
            )
            total_produced = sum(s['produced'] for s in stage_summaries)
            pdf.add_kpis([
                ('إجمالي الكمية المخططة', f"{total_planned:,} قطعة"),
                ('عدد أنواع الموديل', f"{len(variants_data):,} نوع"),
                ('عدد مراحل التشغيل', f"{len(stage_summaries):,} مرحلة"),
            ])

            # Stage Progress Table
            pdf.add_section_title('تقدم مراحل الإنتاج والأسعار')
            stage_rows = []
            for s in stage_summaries:
                stage_rows.append([
                    s['stage'].name,
                    f"{s['unit_price']:,.2f} ج.م",
                    f"{s['planned']:,}",
                    f"{s['produced']:,}",
                    f"{s['remaining']:,}",
                    f"{s['pct']}%",
                ])
            pdf.add_table(
                headers=['المرحلة', 'سعر القطعة', 'المخطط', 'المنتج', 'المتبقي', 'نسبة الإنجاز'],
                rows=stage_rows,
                col_widths=[145, 80, 80, 80, 80, 70],
                right_align_cols=[0]
            )

            # Variants Table with QR Codes
            pdf.add_section_title('أنواع المنتج والكميات المخططة وأكواد QR')
            variant_rows = []
            for item in variants_data:
                qr_img = generate_qr_image_flowable(item['entry_url'], size=36)
                variant_rows.append([
                    item['variant'].sku,
                    item['variant'].color.name,
                    item['variant'].size.name,
                    f"{item['variant'].planned_quantity:,} قطعة",
                    qr_img,
                ])
            pdf.add_table(
                headers=['كود SKU', 'اللون', 'المقاس', 'الكمية المخططة', 'رمز QR'],
                rows=variant_rows,
                col_widths=[125, 110, 110, 110, 80],
                right_align_cols=[1, 2]
            )

            # Recent Production Entries Table
            if recent_entries:
                pdf.add_section_title('آخر سجلات الإنتاج المسجلة لهذا الموديل')
                entry_rows = []
                for e in recent_entries:
                    entry_rows.append([
                        str(e.production_date),
                        f"{e.variant.color.name} / {e.variant.size.name}",
                        e.stage.name,
                        e.worker.name,
                        f"{e.quantity:,}",
                        f"{e.total_amount:,.2f} ج.م",
                    ])
                pdf.add_table(
                    headers=['التاريخ', 'النوع', 'المرحلة', 'العامل', 'الكمية', 'القيمة'],
                    rows=entry_rows,
                    col_widths=[75, 110, 110, 110, 60, 70],
                    right_align_cols=[1, 2, 3]
                )

            return pdf.build_response(f'model_{model.code}_report.pdf')

        return render(request, 'catalog/models/detail.html', {
            'model': model,
            'stage_summaries': stage_summaries,
            'variants_data': variants_data,
            'recent_entries': recent_entries,
            'total_planned': total_planned,
        })


@login_required
def model_toggle(request, pk):
    model = get_object_or_404(ProductModel, pk=pk)
    model.is_active = not model.is_active
    model.save()
    messages.success(request, f'تم {"تفعيل" if model.is_active else "تعطيل"} الموديل.')
    return redirect('catalog:model_detail', pk=pk)


@method_decorator(login_required, name='dispatch')
class VariantUpdateView(View):
    """Update planned quantity for a variant."""
    def post(self, request, pk):
        variant = get_object_or_404(ProductVariant, pk=pk)
        form = ProductVariantPlanForm(request.POST, instance=variant)
        if form.is_valid():
            form.save()
            messages.success(request, f'تم تحديث الكمية المخططة للنوع: {variant.display_name}')
        return redirect('catalog:model_detail', pk=variant.product_model.pk)


@method_decorator(login_required, name='dispatch')
class VariantQRImageView(View):
    """Returns dynamic PNG image of the QR code for a variant."""
    def get(self, request, pk):
        variant = get_object_or_404(ProductVariant.objects.select_related('product_model'), pk=pk)
        base_url = request.build_absolute_uri('/')
        entry_url = build_variant_entry_url(variant, base_url)
        png_bytes = generate_qr_png_bytes(entry_url)
        return HttpResponse(png_bytes, content_type='image/png')


@method_decorator(login_required, name='dispatch')
class VariantQRCardView(View):
    """Printable QR label card for a single variant."""
    def get(self, request, pk):
        variant = get_object_or_404(
            ProductVariant.objects.select_related('product_model__client', 'color', 'size'),
            pk=pk
        )
        base_url = request.build_absolute_uri('/')
        entry_url = build_variant_entry_url(variant, base_url)
        qr_b64 = generate_qr_base64(entry_url)
        return render(request, 'catalog/models/qr_card.html', {
            'variant': variant,
            'entry_url': entry_url,
            'qr_b64': qr_b64,
        })


@method_decorator(login_required, name='dispatch')
class ModelQRSheetView(View):
    """Printable sheet with QR label cards for all variants of a product model."""
    def get(self, request, pk):
        model = get_object_or_404(
            ProductModel.objects.select_related('client').prefetch_related('variants__color', 'variants__size'),
            pk=pk
        )
        base_url = request.build_absolute_uri('/')
        cards = []
        for v in model.variants.all():
            entry_url = build_variant_entry_url(v, base_url)
            qr_b64 = generate_qr_base64(entry_url)
            cards.append({
                'variant': v,
                'entry_url': entry_url,
                'qr_b64': qr_b64,
            })
        return render(request, 'catalog/models/qr_sheet.html', {
            'model': model,
            'cards': cards,
        })

