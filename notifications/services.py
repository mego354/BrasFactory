"""
Notification & Telegram Bot Services:
- OTP generation and Telegram/SMS delivery.
- Comprehensive Telegram Bot engine:
  * Contact/Phone-based simple 1-tap login (request_contact).
  * Worker, Client, and Admin role-based interactive menus.
  * Direct in-chat PDF report downloads.
  * Secure single-use magic web login links.
"""
import io
import re
import random
import string
import logging
from datetime import timedelta
import requests

from django.utils import timezone
from django.conf import settings
from django.db.models import Sum, Count

from catalog.models import Client, ProductModel, ProductVariant
from workers.models import Worker
from workers.services import get_worker_earnings, get_worker_production_history
from production.models import ProductionEntry
from core.utils import get_current_month_date_range
from core.pdf import FactoryPDFReport, FACTORY_INFO
from .models import OTPRecord, TelegramProfile, MagicLoginToken

logger = logging.getLogger(__name__)


def normalize_phone(phone: str) -> str:
    """Normalizes phone numbers for consistent matching."""
    if not phone:
        return ''
    cleaned = re.sub(r'[^\d+]', '', str(phone).strip())
    # Strip international Egyptian prefix if present: +20 or 0020
    if cleaned.startswith('+20'):
        cleaned = '0' + cleaned[3:]
    elif cleaned.startswith('0020'):
        cleaned = '0' + cleaned[4:]
    elif cleaned.startswith('20') and len(cleaned) == 12:
        cleaned = '0' + cleaned[2:]
    return cleaned


def find_entity_by_phone(phone: str):
    """
    Finds matching Client or Worker by phone number.
    Returns (entity_type, entity_obj, display_name).
    """
    clean_p = normalize_phone(phone)
    if not clean_p:
        return None, None, ''

    # 1. Match Worker
    w = Worker.objects.filter(is_active=True).filter(
        phone__icontains=clean_p
    ).first()
    if not w and len(clean_p) > 9:
        w = Worker.objects.filter(is_active=True).filter(
            phone__endswith=clean_p[-9:]
        ).first()

    if w:
        return 'worker', w, w.name

    # 2. Match Client
    cl = Client.objects.filter(is_active=True).filter(
        phone__icontains=clean_p
    ).first()
    if not cl and len(clean_p) > 9:
        cl = Client.objects.filter(is_active=True).filter(
            phone__endswith=clean_p[-9:]
        ).first()

    if cl:
        return 'client', cl, cl.name

    return None, None, ''


# ─────────────────────────────────────────────────────────────
# Telegram Bot API Wrapper
# ─────────────────────────────────────────────────────────────
class TelegramBot:
    """Wrapper for Telegram Bot HTTP API calls."""

    @classmethod
    def get_token(cls):
        return getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or ''

    @classmethod
    def is_configured(cls):
        return bool(cls.get_token())

    @classmethod
    def api_url(cls, method: str):
        return f"https://api.telegram.org/bot{cls.get_token()}/{method}"

    @classmethod
    def send_message(cls, chat_id, text, reply_markup=None):
        token = cls.get_token()
        if not token:
            logger.info(f"[TELEGRAM DEV BOT -> {chat_id}] {text}")
            return {'ok': True, 'dev_mode': True}

        payload = {
            'chat_id': str(chat_id),
            'text': text,
            'parse_mode': 'HTML',
        }
        if reply_markup:
            payload['reply_markup'] = reply_markup

        try:
            resp = requests.post(cls.api_url('sendMessage'), json=payload, timeout=10)
            return resp.json()
        except Exception as e:
            logger.error(f"Telegram sendMessage error: {e}")
            return {'ok': False, 'error': str(e)}

    @classmethod
    def send_document(cls, chat_id, document_bytes: bytes, filename: str, caption: str = ''):
        token = cls.get_token()
        if not token:
            logger.info(f"[TELEGRAM DEV BOT DOC -> {chat_id}] {filename} ({len(document_bytes)} bytes)")
            return {'ok': True, 'dev_mode': True}

        try:
            files = {
                'document': (filename, document_bytes, 'application/pdf')
            }
            data = {
                'chat_id': str(chat_id),
                'caption': caption,
                'parse_mode': 'HTML'
            }
            resp = requests.post(cls.api_url('sendDocument'), data=data, files=files, timeout=25)
            return resp.json()
        except Exception as e:
            logger.error(f"Telegram sendDocument error: {e}")
            return {'ok': False, 'error': str(e)}


# ─────────────────────────────────────────────────────────────
# Interactive Keyboards
# ─────────────────────────────────────────────────────────────
def get_login_keyboard():
    """Contact Request Keyboard for 1-tap phone login."""
    return {
        'keyboard': [
            [{'text': '📱 تسجيل الدخول عبر رقم الهاتف', 'request_contact': True}],
            [{'text': '❓ المساعدة والدعم'}],
        ],
        'resize_keyboard': True,
        'one_time_keyboard': True
    }


def get_worker_keyboard():
    """Worker Main Menu."""
    return {
        'keyboard': [
            [{'text': '💰 أرباح ومستحقات اليوم والشهر'}],
            [{'text': '📋 سجل الإنتاج الأخير'}, {'text': '📄 كشف حساب مفصل (PDF)'}],
            [{'text': '🔗 فتح لوحة التحكم على الويب'}, {'text': '🚪 تسجيل خروج'}],
        ],
        'resize_keyboard': True
    }


def get_client_keyboard():
    """Client Main Menu."""
    return {
        'keyboard': [
            [{'text': '📦 تقدم الموديلات والطلبيات'}],
            [{'text': '📊 ملخص الحساب والقيمة'}, {'text': '📄 تحميل تقرير الإنتاج (PDF)'}],
            [{'text': '🔗 فتح لوحة المتابعة على الويب'}, {'text': '🚪 تسجيل خروج'}],
        ],
        'resize_keyboard': True
    }


def get_admin_keyboard():
    """Admin / Supervisor Main Menu."""
    return {
        'keyboard': [
            [{'text': '🏭 ملخص إنتاج المصنع اليوم'}],
            [{'text': '📊 تقرير الشهر العام'}, {'text': '📄 تحميل تقرير المصنع (PDF)'}],
            [{'text': '🔗 الدخول للوحة الإدارة'}, {'text': '🚪 تسجيل خروج'}],
        ],
        'resize_keyboard': True
    }


# ─────────────────────────────────────────────────────────────
# Bot Update Processor & Dispatcher
# ─────────────────────────────────────────────────────────────
def process_telegram_update(update: dict, base_url: str = 'http://127.0.0.1:8000') -> dict:
    """
    Processes incoming Telegram update payload (from Webhook or Polling).
    Returns result dict with action taken and response status.
    """
    message = update.get('message') or update.get('edited_message')
    if not message:
        return {'status': 'ignored_non_message'}

    chat = message.get('chat', {})
    chat_id = str(chat.get('id', ''))
    if not chat_id:
        return {'status': 'missing_chat_id'}

    from_user = message.get('from', {})
    first_name = from_user.get('first_name', '')
    username = from_user.get('username', '')
    text = (message.get('text') or '').strip()
    contact = message.get('contact')

    # Get or create profile
    profile, _ = TelegramProfile.objects.get_or_create(
        chat_id=chat_id,
        defaults={'first_name': first_name, 'username': username}
    )
    if first_name and profile.first_name != first_name:
        profile.first_name = first_name
        profile.save()

    # 1. Handle Contact Sharing
    if contact:
        phone = contact.get('phone_number', '')
        return handle_contact_login(profile, phone, base_url)

    # 2. Handle /start or /login
    if text.startswith('/start') or text == 'تسجيل الدخول':
        return handle_start_command(profile, text, base_url)

    # 3. Handle Logout
    if text in ('🚪 تسجيل خروج', '/logout'):
        profile.entity_type = ''
        profile.entity_id = None
        profile.phone = ''
        profile.is_authenticated = False
        profile.save()
        TelegramBot.send_message(
            profile.chat_id,
            "👋 تم تسجيل خروجك بنجاح.\nلإعادة تسجيل الدخول، اضغط على الزر أدناه لمشاركة رقم الهاتف.",
            reply_markup=get_login_keyboard()
        )
        return {'status': 'logged_out'}

    # 4. Handle Help
    if text in ('❓ المساعدة والدعم', '/help'):
        help_msg = (
            f"🏭 <b>{FACTORY_INFO['name']}</b>\n"
            f"بوت المتابعة والخدمات الذاتية للعملاء والعمال.\n\n"
            f"🔹 للبدء: شارك رقم هاتفك المسجل لتسجيل الدخول الفوري.\n"
            f"🔹 الخدمات المتاحة:\n"
            f"  • متابعة الأرباح وحسابات الإنتاج.\n"
            f"  • الاستعلام عن موقف الموديلات والطلبيات.\n"
            f"  • تحميل التقارير وكشوف الحساب بصيغة PDF مباشرة.\n"
            f"  • روابط دخول سريعة ومؤمنة للوحة التحكم على الويب."
        )
        TelegramBot.send_message(profile.chat_id, help_msg)
        return {'status': 'help_sent'}

    # 5. If not authenticated, check if user typed a phone number
    if not profile.is_authenticated:
        cleaned_phone = normalize_phone(text)
        if len(cleaned_phone) >= 10 and cleaned_phone.isdigit():
            return handle_contact_login(profile, cleaned_phone, base_url)

        TelegramBot.send_message(
            profile.chat_id,
            f"👋 أهلاً بك في نظام <b>{FACTORY_INFO['name']}</b>.\n\n"
            f"يرجى تسجيل الدخول عن طريق مشاركة رقم هاتفك المسجل في المصنع للوصول إلى حسابك.",
            reply_markup=get_login_keyboard()
        )
        return {'status': 'prompted_login'}

    # 6. Dispatch role-specific actions
    if profile.entity_type == 'worker':
        return handle_worker_action(profile, text, base_url)
    elif profile.entity_type == 'client':
        return handle_client_action(profile, text, base_url)
    elif profile.entity_type == 'admin':
        return handle_admin_action(profile, text, base_url)

    return {'status': 'unknown_action'}


# ─────────────────────────────────────────────────────────────
# Handlers: Login & Role Menus
# ─────────────────────────────────────────────────────────────
def handle_contact_login(profile: TelegramProfile, phone: str, base_url: str) -> dict:
    """Validates contact phone number and binds entity to TelegramProfile."""
    entity_type, entity_obj, display_name = find_entity_by_phone(phone)

    if not entity_obj:
        msg = (
            f"⚠️ عذراً، رقم الهاتف <code>{phone}</code> غير مسجل في نظام المصنع.\n\n"
            f"يرجى التواصل مع إدارة المصنع لإضافة رقمك في سجلات العمال أو العملاء."
        )
        TelegramBot.send_message(profile.chat_id, msg, reply_markup=get_login_keyboard())
        return {'status': 'phone_not_found'}

    profile.phone = normalize_phone(phone)
    profile.entity_type = entity_type
    profile.entity_id = entity_obj.pk
    profile.is_authenticated = True
    profile.save()

    role_label = 'عامل إنتاج' if entity_type == 'worker' else 'عميل'
    keyboard = get_worker_keyboard() if entity_type == 'worker' else get_client_keyboard()

    welcome_msg = (
        f"✅ <b>تم التحقق بنجاح!</b>\n\n"
        f"مرحباً بك يا <b>{display_name}</b> ({role_label}).\n"
        f"يمكنك الآن استخدام القائمة أدناه للاستعلام، أو تحميل كشوف الحساب PDF، أو الدخول المباشر للويب."
    )
    TelegramBot.send_message(profile.chat_id, welcome_msg, reply_markup=keyboard)
    return {'status': 'authenticated', 'entity_type': entity_type, 'name': display_name}


def handle_start_command(profile: TelegramProfile, text: str, base_url: str) -> dict:
    """Handles /start command with auto-routing."""
    if profile.is_authenticated and profile.entity_id:
        if profile.entity_type == 'worker':
            w = Worker.objects.filter(pk=profile.entity_id, is_active=True).first()
            if w:
                TelegramBot.send_message(
                    profile.chat_id,
                    f"👷 مرحباً <b>{w.name}</b>! اختر الخدمة المطلوبة من القائمة:",
                    reply_markup=get_worker_keyboard()
                )
                return {'status': 'worker_menu_sent'}
        elif profile.entity_type == 'client':
            cl = Client.objects.filter(pk=profile.entity_id, is_active=True).first()
            if cl:
                TelegramBot.send_message(
                    profile.chat_id,
                    f"👥 مرحباً <b>{cl.name}</b>! اختر الخدمة المطلوبة من القائمة:",
                    reply_markup=get_client_keyboard()
                )
                return {'status': 'client_menu_sent'}

    # Not logged in
    welcome_text = (
        f"🏭 <b>مرحباً بك في نظام {FACTORY_INFO['name']}</b>\n"
        f"نظام متابعة الإنتاج والخدمات الإلكترونية.\n\n"
        f"اضغط على زر <b>'📱 تسجيل الدخول عبر رقم الهاتف'</b> بالأسفل لبدء الاستخدام."
    )
    TelegramBot.send_message(profile.chat_id, welcome_text, reply_markup=get_login_keyboard())
    return {'status': 'start_prompt'}


# ─────────────────────────────────────────────────────────────
# Worker Service Actions
# ─────────────────────────────────────────────────────────────
def handle_worker_action(profile: TelegramProfile, text: str, base_url: str) -> dict:
    worker = Worker.objects.filter(pk=profile.entity_id).first()
    if not worker:
        profile.is_authenticated = False
        profile.save()
        TelegramBot.send_message(profile.chat_id, "⚠️ تم إيقاف الحساب أو حذفه.", reply_markup=get_login_keyboard())
        return {'status': 'worker_not_found'}

    today = timezone.localdate()
    start_date, end_date = get_current_month_date_range()

    # 1. Earnings Summary
    t_low = text.lower()
    if 'أرباح' in text or 'مستحقات' in text or t_low in ('/earnings', 'earnings', '/stats', 'stats'):
        today_entries = ProductionEntry.objects.filter(worker=worker, production_date=today, is_cancelled=False)
        today_qty = today_entries.aggregate(q=Sum('quantity'))['q'] or 0
        today_val = today_entries.aggregate(v=Sum('total_amount'))['v'] or 0

        month_summary = get_worker_earnings(worker, start_date, end_date)

        msg = (
            f"💰 <b>بيان أرباح ومستحقات: {worker.name}</b>\n\n"
            f"📅 <b>إنتاج اليوم ({today}):</b>\n"
            f"  • القطع المنتجة: <b>{today_qty:,}</b> قطعة\n"
            f"  • مستحقات اليوم: <b>{today_val:,.2f} ج.م</b>\n\n"
            f"📊 <b>إجمالي الشهر الحالي ({start_date} إلى {end_date}):</b>\n"
            f"  • إجمالي القطع: <b>{month_summary['total_qty']:,}</b> قطعة\n"
            f"  • إجمالي الأرباح: <b>{month_summary['total_amount']:,.2f} ج.م</b>\n"
            f"  • عدد السجلات: <b>{month_summary['entry_count']:,}</b> سجل"
        )
        TelegramBot.send_message(profile.chat_id, msg, reply_markup=get_worker_keyboard())
        return {'status': 'worker_earnings_sent'}

    # 2. Recent Production Log
    if 'سجل الإنتاج' in text or t_low in ('/history', 'history', '/log', 'log'):
        history = get_worker_production_history(worker, start_date, end_date)[:5]
        if not history:
            TelegramBot.send_message(profile.chat_id, "📋 لا توجد سجلات إنتاج مسجلة لهذا الشهر حتى الآن.")
            return {'status': 'no_history'}

        lines = [f"📋 <b>آخر سجلات الإنتاج للعامل {worker.name}:</b>\n"]
        for e in history:
            lines.append(
                f"• {e.production_date} | {e.variant.product_model.code} ({e.variant.color.name}/{e.variant.size.name}) | {e.stage.name}\n"
                f"  الكمية: <b>{e.quantity:,}</b> قطعة | الأرباح: <b>{e.total_amount:,.2f} ج.م</b>"
            )
        TelegramBot.send_message(profile.chat_id, "\n\n".join(lines), reply_markup=get_worker_keyboard())
        return {'status': 'worker_history_sent'}

    # 3. Direct PDF Download
    if 'PDF' in text or 'كشف حساب' in text or t_low in ('/pdf', 'pdf', '/report', 'report'):
        summary = get_worker_earnings(worker, start_date, end_date)
        history = get_worker_production_history(worker, start_date, end_date)

        pdf = FactoryPDFReport(
            title=f'كشف إنتاج ومستحقات العامل: {worker.name}',
            subtitle=f'الفترة من {start_date} إلى {end_date}'
        )
        stage_names = "، ".join([s.name for s in worker.stages.all()]) or 'غير مسند'
        pdf.add_header(filters_dict={
            'العامل': worker.name,
            'الهاتف': worker.phone or '—',
            'المراحل': stage_names,
            'الفترة': f'{start_date} إلى {end_date}',
        })
        pdf.add_kpis([
            ('إجمالي القطع', f"{summary['total_qty']:,} قطعة"),
            ('إجمالي الأرباح', f"{summary['total_amount']:,.2f} ج.م"),
            ('عدد السجلات', f"{summary['entry_count']:,} سجل"),
        ])

        if history:
            pdf.add_section_title('تفاصيل سجل الإنتاج والأرباح')
            h_rows = []
            for e in history:
                h_rows.append([
                    str(e.production_date),
                    e.variant.product_model.code,
                    f"{e.variant.color.name} / {e.variant.size.name}",
                    e.stage.name,
                    f"{e.quantity:,}",
                    f"{e.total_amount:,.2f} ج.م",
                ])
            pdf.add_table(
                headers=['التاريخ', 'الموديل', 'النوع', 'المرحلة', 'الكمية', 'الأرباح'],
                rows=h_rows,
                col_widths=[75, 80, 135, 115, 60, 70],
                right_align_cols=[2, 3]
            )

        doc_bytes = pdf.buffer.getvalue()
        pdf.buffer.close()

        TelegramBot.send_document(
            profile.chat_id,
            doc_bytes,
            f"worker_statement_{worker.pk}_{start_date}.pdf",
            caption=f"📄 كشف حساب ومستحقات العامل: {worker.name}\nالفترة: {start_date} إلى {end_date}"
        )
        return {'status': 'worker_pdf_sent'}

    # 4. Web Portal Magic Login Link
    if 'الويب' in text or 'لوحة' in text or t_low in ('/web', 'web', '/link', 'link'):
        token_obj = MagicLoginToken.create_token('worker', worker.pk, worker.name)
        login_url = f"{base_url.rstrip('/')}/notifications/magic-login/{token_obj.token}/"
        msg = (
            f"🔗 <b>رابط الدخول المباشر إلى لوحة العامل على الويب:</b>\n\n"
            f"<a href='{login_url}'>👉 اضغط هنا لفتح لوحة التحكم مباشرة</a>\n\n"
            f"⏳ <i>هذا الرابط صالح لمرة واحدة خلال 15 دقيقة فقط.</i>"
        )
        TelegramBot.send_message(profile.chat_id, msg, reply_markup=get_worker_keyboard())
        return {'status': 'worker_magic_link_sent'}

    return {'status': 'unrecognized_worker_command'}


# ─────────────────────────────────────────────────────────────
# Client Service Actions
# ─────────────────────────────────────────────────────────────
def handle_client_action(profile: TelegramProfile, text: str, base_url: str) -> dict:
    client = Client.objects.filter(pk=profile.entity_id).first()
    if not client:
        profile.is_authenticated = False
        profile.save()
        TelegramBot.send_message(profile.chat_id, "⚠️ تم إيقاف حساب العميل.", reply_markup=get_login_keyboard())
        return {'status': 'client_not_found'}

    start_date, end_date = get_current_month_date_range()

    # 1. Models & Order Progress
    t_low = text.lower()
    if 'الموديلات' in text or 'الطلبيات' in text or t_low in ('/models', 'models', '/orders', 'orders'):
        models = client.product_models.filter(is_active=True).prefetch_related('variants', 'model_stages__stage')
        if not models:
            TelegramBot.send_message(profile.chat_id, "📦 لا توجد موديلات مسجلة حالياً.")
            return {'status': 'no_models'}

        lines = [f"📦 <b>موقف موديلات وطلبيات: {client.name}</b>\n"]
        for m in models:
            produced_qty = ProductionEntry.objects.filter(variant__product_model=m, is_cancelled=False).aggregate(q=Sum('quantity'))['q'] or 0
            planned = m.total_planned
            pct = round((produced_qty / planned * 100), 1) if planned > 0 else 0
            lines.append(
                f"• <b>{m.code} — {m.name}</b>\n"
                f"  المخطط: <b>{planned:,}</b> | المنفذ: <b>{produced_qty:,}</b> ({pct}%)\n"
                f"  الأنواع: <b>{m.variants.count()}</b> نوع"
            )
        TelegramBot.send_message(profile.chat_id, "\n\n".join(lines), reply_markup=get_client_keyboard())
        return {'status': 'client_models_sent'}

    # 2. Account & Value Summary
    if 'ملخص الحساب' in text or 'القيمة' in text or t_low in ('/summary', 'summary', '/stats', 'stats'):
        entries = ProductionEntry.objects.filter(variant__product_model__client=client, is_cancelled=False)
        total_qty = entries.aggregate(q=Sum('quantity'))['q'] or 0
        total_val = entries.aggregate(v=Sum('total_amount'))['v'] or 0
        models_count = client.product_models.count()

        msg = (
            f"📊 <b>ملخص حساب الإنتاج: {client.name}</b>\n\n"
            f"• كود العميل: <code>{client.code}</code>\n"
            f"• إجمالي القطع المنتجة: <b>{total_qty:,}</b> قطعة\n"
            f"• إجمالي قيمة الإنتاج: <b>{total_val:,.2f} ج.م</b>\n"
            f"• عدد الموديلات: <b>{models_count:,}</b> موديل"
        )
        TelegramBot.send_message(profile.chat_id, msg, reply_markup=get_client_keyboard())
        return {'status': 'client_summary_sent'}

    # 3. Direct PDF Download
    if 'PDF' in text or 'تقرير' in text or t_low in ('/pdf', 'pdf', '/report', 'report'):
        entries = ProductionEntry.objects.filter(variant__product_model__client=client, is_cancelled=False)
        total_qty = entries.aggregate(q=Sum('quantity'))['q'] or 0
        total_val = entries.aggregate(v=Sum('total_amount'))['v'] or 0
        models = client.product_models.filter(is_active=True).prefetch_related('variants')
        recent = entries.select_related('variant__color', 'variant__size', 'stage').order_by('-production_date')[:25]

        pdf = FactoryPDFReport(
            title=f'كشف إنتاج ومتابعة طلبيات العميل: {client.name}',
            subtitle=f'الفترة من {start_date} إلى {end_date}'
        )
        pdf.add_header(filters_dict={
            'العميل': client.name,
            'كود العميل': client.code,
            'الفترة': f'{start_date} إلى {end_date}',
        })
        pdf.add_kpis([
            ('إجمالي القطع', f"{total_qty:,} قطعة"),
            ('إجمالي القيمة', f"{total_val:,.2f} ج.م"),
            ('عدد الموديلات', f"{models.count():,} موديل"),
        ])

        if models:
            pdf.add_section_title('الموديلات المسجلة وخطة الإنتاج')
            m_rows = []
            for m in models:
                m_rows.append([m.code, m.name, f"{m.variants.count()} نوع", f"{m.total_planned:,} قطعة"])
            pdf.add_table(
                headers=['الكود', 'اسم الموديل', 'الأنواع', 'إجمالي المخطط'],
                rows=m_rows,
                col_widths=[95, 220, 105, 115],
                right_align_cols=[1]
            )

        if recent:
            pdf.add_section_title('سجل عمليات الإنتاج')
            e_rows = []
            for e in recent:
                e_rows.append([
                    str(e.production_date),
                    e.variant.product_model.code,
                    f"{e.variant.color.name} / {e.variant.size.name}",
                    e.stage.name,
                    f"{e.quantity:,}",
                ])
            pdf.add_table(
                headers=['التاريخ', 'الموديل', 'النوع', 'المرحلة', 'الكمية'],
                rows=e_rows,
                col_widths=[85, 90, 175, 115, 70],
                right_align_cols=[2, 3]
            )

        doc_bytes = pdf.buffer.getvalue()
        pdf.buffer.close()

        TelegramBot.send_document(
            profile.chat_id,
            doc_bytes,
            f"client_report_{client.code}_{start_date}.pdf",
            caption=f"📄 تقرير إنتاج وطلبيات العميل: {client.name}\nالفترة: {start_date} إلى {end_date}"
        )
        return {'status': 'client_pdf_sent'}

    # 4. Web Portal Magic Login Link
    if 'الويب' in text or 'لوحة' in text or t_low in ('/web', 'web', '/link', 'link'):
        token_obj = MagicLoginToken.create_token('client', client.pk, client.name)
        login_url = f"{base_url.rstrip('/')}/notifications/magic-login/{token_obj.token}/"
        msg = (
            f"🔗 <b>رابط الدخول المباشر إلى لوحة العميل على الويب:</b>\n\n"
            f"<a href='{login_url}'>👉 اضغط هنا لفتح لوحة المتابعة مباشرة</a>\n\n"
            f"⏳ <i>هذا الرابط صالح لمرة واحدة خلال 15 دقيقة فقط.</i>"
        )
        TelegramBot.send_message(profile.chat_id, msg, reply_markup=get_client_keyboard())
        return {'status': 'client_magic_link_sent'}

    return {'status': 'unrecognized_client_command'}


# ─────────────────────────────────────────────────────────────
# Admin / Supervisor Service Actions
# ─────────────────────────────────────────────────────────────
def handle_admin_action(profile: TelegramProfile, text: str, base_url: str) -> dict:
    today = timezone.localdate()
    start_date, end_date = get_current_month_date_range()
    t_low = text.lower()

    if 'اليوم' in text or t_low in ('/today', 'today', '/daily', 'daily'):
        entries = ProductionEntry.objects.filter(production_date=today, is_cancelled=False)
        total_qty = entries.aggregate(q=Sum('quantity'))['q'] or 0
        total_val = entries.aggregate(v=Sum('total_amount'))['v'] or 0
        workers_count = entries.values('worker').distinct().count()

        msg = (
            f"🏭 <b>ملخص إنتاج المصنع اليوم ({today}):</b>\n\n"
            f"• القطع المنتجة: <b>{total_qty:,}</b> قطعة\n"
            f"• القيمة المحققة: <b>{total_val:,.2f} ج.م</b>\n"
            f"• العمال النشطون اليوم: <b>{workers_count:,}</b> عامل"
        )
        TelegramBot.send_message(profile.chat_id, msg, reply_markup=get_admin_keyboard())
        return {'status': 'admin_today_sent'}

    if 'الشهر' in text or t_low in ('/month', 'month', '/stats', 'stats'):
        entries = ProductionEntry.objects.filter(production_date__gte=start_date, production_date__lte=end_date, is_cancelled=False)
        total_qty = entries.aggregate(q=Sum('quantity'))['q'] or 0
        total_val = entries.aggregate(v=Sum('total_amount'))['v'] or 0
        active_models = ProductModel.objects.filter(is_active=True).count()

        msg = (
            f"📊 <b>ملخص إنتاج الشهر ({start_date} إلى {end_date}):</b>\n\n"
            f"• إجمالي القطع: <b>{total_qty:,}</b> قطعة\n"
            f"• إجمالي القيمة: <b>{total_val:,.2f} ج.م</b>\n"
            f"• الموديلات النشطة: <b>{active_models:,}</b> موديل"
        )
        TelegramBot.send_message(profile.chat_id, msg, reply_markup=get_admin_keyboard())
        return {'status': 'admin_month_sent'}

    if 'PDF' in text or 'المصنع' in text or t_low in ('/pdf', 'pdf', '/report', 'report'):
        entries = ProductionEntry.objects.filter(production_date__gte=start_date, production_date__lte=end_date, is_cancelled=False)
        total_qty = entries.aggregate(q=Sum('quantity'))['q'] or 0
        total_val = entries.aggregate(v=Sum('total_amount'))['v'] or 0

        pdf = FactoryPDFReport(
            title='تقرير متابعة وسجل الإنتاج العام للمصنع',
            subtitle=f'الفترة من {start_date} إلى {end_date}'
        )
        pdf.add_header(filters_dict={'الفترة': f'{start_date} إلى {end_date}'})
        pdf.add_kpis([
            ('إجمالي القطع', f"{total_qty:,} قطعة"),
            ('إجمالي القيمة', f"{total_val:,.2f} ج.م"),
            ('عدد السجلات', f"{entries.count():,} سجل"),
        ])
        doc_bytes = pdf.buffer.getvalue()
        pdf.buffer.close()

        TelegramBot.send_document(
            profile.chat_id,
            doc_bytes,
            f"factory_report_{start_date}_{end_date}.pdf",
            caption=f"📄 تقرير الإنتاج الشامل للمصنع ({start_date} إلى {end_date})"
        )
        return {'status': 'admin_pdf_sent'}

    return {'status': 'unrecognized_admin_command'}


# ─────────────────────────────────────────────────────────────
# OTP Delivery via Telegram
# ─────────────────────────────────────────────────────────────
class OTPProvider:
    def send(self, phone: str, otp: str, name: str) -> bool:
        raise NotImplementedError


class TelegramOTPProvider(OTPProvider):
    def send(self, phone: str, otp: str, name: str) -> bool:
        clean_p = normalize_phone(phone)
        profile = TelegramProfile.objects.filter(phone=clean_p, is_authenticated=True).first()

        message = (
            f"🏭 <b>{FACTORY_INFO['name']}</b>\n\n"
            f"مرحباً <b>{name}</b>،\n"
            f"رمز التحقق السريع الخاص بك هو:\n\n"
            f"🔐 <code>{otp}</code>\n\n"
            f"صالح لمدة {settings.OTP_EXPIRY_MINUTES} دقائق."
        )

        if profile:
            res = TelegramBot.send_message(profile.chat_id, message)
            logger.info(f"Telegram OTP sent to chat {profile.chat_id}")
            return res.get('ok', False)
        else:
            # Broadcast to dev console if not linked
            print(f"\n{'='*50}\n📱 OTP للمستخدم {name} ({phone}): {otp}\n{'='*50}\n")
            return True


_provider = TelegramOTPProvider()


def generate_otp(length: int = 6) -> str:
    return ''.join(random.choices(string.digits, k=length))


def create_and_send_otp(phone: str, entity_type: str, entity_id: int, name: str) -> bool:
    rate_limit_minutes = getattr(settings, 'OTP_RATE_LIMIT_MINUTES', 60)
    since = timezone.now() - timedelta(minutes=rate_limit_minutes)

    otp = generate_otp()
    expiry = timezone.now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

    OTPRecord.objects.filter(phone=phone, is_used=False).update(is_used=True)

    OTPRecord.objects.create(
        phone=phone,
        otp_hash=OTPRecord.hash_otp(otp),
        entity_type=entity_type,
        entity_id=entity_id,
        expires_at=expiry,
    )

    return _provider.send(phone, otp, name)


def verify_otp(phone: str, otp: str) -> OTPRecord | None:
    try:
        record = OTPRecord.objects.filter(phone=phone, is_used=False).latest('created_at')
    except OTPRecord.DoesNotExist:
        return None

    if record.is_expired or record.is_locked:
        return None

    record.attempt_count += 1
    if record.verify(otp):
        record.is_used = True
        record.save()
        return record
    else:
        record.save()
        return None
