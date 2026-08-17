"""
Notification & Telegram Web Views:
- TelegramWebhookView: Webhook receiver for Telegram Bot updates.
- MagicLoginView: Single-use one-click web authentication from Telegram.
"""
import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.views import View
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone

from .models import MagicLoginToken, TelegramProfile
from .services import process_telegram_update
from external.views import EXTERNAL_SESSION_KEY

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class TelegramWebhookView(View):
    """Webhook endpoint for Telegram Bot API updates."""

    def post(self, request):
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception as e:
            return JsonResponse({'status': 'invalid_json', 'error': str(e)}, status=400)

        base_url = request.build_absolute_uri('/')
        result = process_telegram_update(payload, base_url=base_url)
        return JsonResponse({'status': 'ok', 'result': result})

    def get(self, request):
        return HttpResponse("Telegram Bot Webhook Endpoint is active.")


class MagicLoginView(View):
    """
    Validates a single-use token from Telegram and authenticates
    the client or worker directly into their dashboard.
    """

    def get(self, request, token):
        try:
            token_obj = MagicLoginToken.objects.get(token=token)
        except MagicLoginToken.DoesNotExist:
            messages.error(request, 'رابط الدخول غير صالح أو انتهت صلاحيته.')
            return redirect('external:otp_request')

        if not token_obj.is_valid:
            messages.error(request, 'عذراً، هذا الرابط مستخدم بالفعل أو انتهت صلاحيته.')
            return redirect('external:otp_request')

        # Mark as used immediately (single-use)
        token_obj.is_used = True
        token_obj.save()

        # Create authenticated external portal session
        request.session[EXTERNAL_SESSION_KEY] = {
            'type': token_obj.entity_type,
            'entity_id': token_obj.entity_id,
            'name': token_obj.name,
            'authenticated_at': timezone.now().isoformat(),
            'source': 'telegram_magic_login',
        }

        messages.success(request, f'أهلاً بك يا {token_obj.name}! تم تسجيل دخولك بنجاح عبر تليجرام.')

        if token_obj.entity_type == 'client':
            return redirect('external:client_dashboard')
        elif token_obj.entity_type == 'worker':
            return redirect('external:worker_dashboard')
        else:
            return redirect('production:dashboard')
