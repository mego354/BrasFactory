"""
External Views — OTP authentication for clients and workers.
Security: Entity identity stored ONLY in server session.
Never trust URL parameters for identity after authentication.
"""
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views import View
from django.db.models import Sum
from django.core.paginator import Paginator
from django.utils import timezone

from catalog.models import Client
from workers.models import Worker
from notifications.services import create_and_send_otp, verify_otp

EXTERNAL_SESSION_KEY = 'external_auth'


def _get_external_entity(session):
    """Safely retrieve authenticated external entity from session."""
    return session.get(EXTERNAL_SESSION_KEY)


class OTPRequestView(View):
    """Phone number entry + entity type selection."""
    template_name = 'external/otp_request.html'

    def get(self, request):
        if _get_external_entity(request.session):
            auth = _get_external_entity(request.session)
            if auth['type'] == 'client':
                return redirect('external:client_dashboard')
            return redirect('external:worker_dashboard')
        return render(request, self.template_name)

    def post(self, request):
        phone = request.POST.get('phone', '').strip()
        entity_type = request.POST.get('entity_type', '').strip()

        if not phone or entity_type not in ('client', 'worker'):
            messages.error(request, 'يرجى إدخال رقم الهاتف واختيار نوع الحساب.')
            return render(request, self.template_name)

        # Normalize phone
        phone = phone.replace(' ', '').replace('-', '')

        # Look up entity
        entity = None
        name = ''
        if entity_type == 'client':
            try:
                entity = Client.objects.get(phone=phone, is_active=True)
                name = entity.name
            except Client.DoesNotExist:
                pass
        else:
            try:
                entity = Worker.objects.get(phone=phone, is_active=True)
                name = entity.name
            except Worker.DoesNotExist:
                pass

        if not entity:
            # Don't reveal whether phone exists (prevent enumeration)
            messages.info(
                request,
                'إذا كان الرقم مسجلاً في النظام، ستتلقى رمز التحقق قريباً.'
            )
            return render(request, self.template_name)

        success = create_and_send_otp(phone, entity_type, entity.pk, name)
        # Store pending verification in session (not authenticated yet)
        request.session['otp_pending'] = {
            'phone': phone,
            'type': entity_type,
            'name': name,
        }

        messages.success(request, 'تم إرسال رمز التحقق. يرجى التحقق من التليجرام.')
        return redirect('external:otp_verify')


class OTPVerifyView(View):
    """OTP code entry and session creation."""
    template_name = 'external/otp_verify.html'

    def get(self, request):
        if not request.session.get('otp_pending'):
            return redirect('external:otp_request')
        return render(request, self.template_name, {
            'pending': request.session['otp_pending'],
            'expiry_minutes': 5,
        })

    def post(self, request):
        pending = request.session.get('otp_pending')
        if not pending:
            return redirect('external:otp_request')

        otp_input = request.POST.get('otp', '').strip()
        phone = pending['phone']

        record = verify_otp(phone, otp_input)

        if not record:
            messages.error(request, 'رمز التحقق غير صحيح أو انتهت صلاحيته. حاول مرة أخرى.')
            return render(request, self.template_name, {
                'pending': pending, 'expiry_minutes': 5
            })

        # Create secure session — entity_id from DB record, not user input
        request.session[EXTERNAL_SESSION_KEY] = {
            'type': record.entity_type,
            'entity_id': record.entity_id,
            'name': pending['name'],
            'authenticated_at': timezone.now().isoformat(),
        }
        del request.session['otp_pending']

        messages.success(request, f'أهلاً {pending["name"]}! تم تسجيل دخولك بنجاح.')

        if record.entity_type == 'client':
            return redirect('external:client_dashboard')
        return redirect('external:worker_dashboard')


class ExternalClientDashboardView(View):
    """Client-only read-only dashboard."""
    template_name = 'external/client_dashboard.html'

    def get(self, request):
        auth = _get_external_entity(request.session)
        if not auth or auth['type'] != 'client':
            return redirect('external:otp_request')

        # Always read client from session — never from URL
        client = Client.objects.get(pk=auth['entity_id'])
        from production.models import ProductionEntry

        start_date = request.GET.get('start_date', '')
        end_date = request.GET.get('end_date', '')

        models = client.product_models.filter(is_active=True).prefetch_related(
            'variants', 'model_stages__stage'
        )

        entries_qs = ProductionEntry.objects.filter(
            variant__product_model__client=client, is_cancelled=False
        )
        if start_date:
            entries_qs = entries_qs.filter(production_date__gte=start_date)
        if end_date:
            entries_qs = entries_qs.filter(production_date__lte=end_date)

        total_value = entries_qs.aggregate(val=Sum('total_amount'))['val'] or 0
        total_qty = entries_qs.aggregate(qty=Sum('quantity'))['qty'] or 0

        recent = entries_qs.select_related(
            'variant__color', 'variant__size', 'stage'
        ).order_by('-production_date')[:20]

        return render(request, self.template_name, {
            'client': client,
            'models': models,
            'total_value': total_value,
            'total_qty': total_qty,
            'recent': recent,
            'start_date': start_date,
            'end_date': end_date,
        })


class ExternalWorkerDashboardView(View):
    """Worker-only read-only dashboard."""
    template_name = 'external/worker_dashboard.html'

    def get(self, request):
        auth = _get_external_entity(request.session)
        if not auth or auth['type'] != 'worker':
            return redirect('external:otp_request')

        worker = Worker.objects.prefetch_related('stages').get(pk=auth['entity_id'])
        from workers.services import get_worker_earnings, get_worker_production_history

        start_date = request.GET.get('start_date', '')
        end_date = request.GET.get('end_date', '')

        summary = get_worker_earnings(worker, start_date or None, end_date or None)
        history = get_worker_production_history(worker, start_date or None, end_date or None)
        paginator = Paginator(history, 20)
        page = paginator.get_page(request.GET.get('page'))

        return render(request, self.template_name, {
            'worker': worker,
            'summary': summary,
            'page_obj': page,
            'start_date': start_date,
            'end_date': end_date,
        })


class ExternalLogoutView(View):
    def get(self, request):
        request.session.pop(EXTERNAL_SESSION_KEY, None)
        request.session.pop('otp_pending', None)
        messages.success(request, 'تم تسجيل خروجك بنجاح.')
        return redirect('external:otp_request')
