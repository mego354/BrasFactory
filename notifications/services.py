"""
Notification & Telegram Bot Services — Red Rose Apparel Factory

- TelegramBot: HTTP API wrapper.
- process_telegram_update: Main dispatcher for webhook updates.
- Worker-only interactive menus (phone-based login, month summaries, magic-link dashboard).
- Admin role-based actions with sorted PDF generation.
- NO OTP. NO client-facing features.
"""
import logging
from datetime import timedelta, date
import calendar
import requests

from django.utils import timezone
from django.conf import settings
from django.db.models import Sum, Count

from workers.models import Worker
from workers.services import get_worker_earnings, get_worker_production_history
from production.models import ProductionEntry
from core.utils import get_current_month_date_range
from core.pdf import FactoryPDFReport, FACTORY_INFO
from .models import TelegramProfile, MagicLoginToken

logger = logging.getLogger(__name__)

ARABIC_MONTHS = [
    '', 'يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو',
    'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'
]


def normalize_phone(phone: str) -> str:
    """Normalizes phone numbers converting Arabic digits and removing country codes."""
    if not phone:
        return ''
    # Convert Arabic numerals to ASCII digits
    arabic_trans = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    phone = str(phone).translate(arabic_trans)
    import re
    cleaned = re.sub(r'[^\d+]', '', phone.strip())
    if cleaned.startswith('+20'):
        cleaned = '0' + cleaned[3:]
    elif cleaned.startswith('0020'):
        cleaned = '0' + cleaned[4:]
    elif cleaned.startswith('20') and len(cleaned) == 12:
        cleaned = '0' + cleaned[2:]
    return cleaned


def find_worker_by_phone(phone: str):
    """
    Finds matching active Worker by phone number with robust matching
    supporting various formats (010..., +20..., spaces, dashes, etc.).
    """
    if not phone:
        return None

    import re
    arabic_trans = str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789')
    raw_str = str(phone).translate(arabic_trans)
    digits = re.sub(r'\D', '', raw_str)
    if not digits:
        return None

    # 1. Clean Egyptian local format (e.g. 01012345678)
    clean_p = normalize_phone(phone)

    # 2. Extract core suffix (last 8-9 digits)
    core_suffix = digits[-8:] if len(digits) >= 8 else digits

    # Try direct database filters
    w = Worker.objects.filter(is_active=True).filter(phone__icontains=core_suffix).first()
    if w:
        return w

    if clean_p:
        w = Worker.objects.filter(is_active=True).filter(phone__icontains=clean_p).first()
        if w:
            return w

    # 3. Comprehensive scan over active workers comparing normalized digits
    for worker in Worker.objects.filter(is_active=True):
        if not worker.phone:
            continue
        w_raw = str(worker.phone).translate(arabic_trans)
        w_digits = re.sub(r'\D', '', w_raw)
        if not w_digits:
            continue
        if w_digits == digits or w_digits.endswith(core_suffix) or digits.endswith(w_digits[-8:] if len(w_digits) >= 8 else w_digits):
            return worker

    return None


# ─────────────────────────────────────────────────────────────
# Telegram Bot API Wrapper
# ─────────────────────────────────────────────────────────────
class TelegramBot:
    """Wrapper for Telegram Bot HTTP API calls."""

    DEFAULT_TOKEN = '8932038793:AAGpPDZAiibxbnHo4-gcKcr8957fczyMhCY'

    @classmethod
    def get_token(cls):
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or ''
        return token if token else cls.DEFAULT_TOKEN

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
            resp = requests.post(cls.api_url('sendMessage'), json=payload, timeout=12)
            data = resp.json()
            if not data.get('ok'):
                logger.error(f"Telegram API response error: {data}")
            return data
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
            files = {'document': (filename, document_bytes, 'application/pdf')}
            data = {'chat_id': str(chat_id), 'caption': caption, 'parse_mode': 'HTML'}
            resp = requests.post(cls.api_url('sendDocument'), data=data, files=files, timeout=25)
            data = resp.json()
            if not data.get('ok'):
                logger.error(f"Telegram sendDocument API response error: {data}")
            return data
        except Exception as e:
            logger.error(f"Telegram sendDocument error: {e}")
            return {'ok': False, 'error': str(e)}


# ─────────────────────────────────────────────────────────────
# Keyboard Layouts
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
    """Worker Main Menu — Red Rose Factory."""
    return {
        'keyboard': [
            [{'text': '📅 إنتاجي اليوم'}],
            [{'text': '📊 إنتاج هذا الشهر'}, {'text': '📊 إنتاج الشهر الماضي'}],
            [{'text': '🌐 فتح لوحة التحكم'}],
            [{'text': '📱 تسجيل إنتاج جديد'}],
            [{'text': '🚪 تسجيل خروج'}],
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


def _get_month_range(year, month):
    """Return (start_date_str, end_date_str) for a given year/month."""
    _, num_days = calendar.monthrange(year, month)
    return date(year, month, 1).isoformat(), date(year, month, num_days).isoformat()


def _last_month():
    today = date.today()
    if today.month == 1:
        return today.year - 1, 12
    return today.year, today.month - 1


# ─────────────────────────────────────────────────────────────
# Bot Update Processor & Dispatcher
# ─────────────────────────────────────────────────────────────
def process_telegram_update(update: dict, base_url: str = 'http://127.0.0.1:8000') -> dict:
    """
    Processes incoming Telegram update payload (from Webhook).
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

    # 1. Handle Contact Sharing (phone-based login)
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
            f"بوت متابعة الإنتاج والخدمات الذاتية للعمال.\n\n"
            f"🔹 للبدء: شارك رقم هاتفك المسجل لتسجيل الدخول الفوري.\n"
            f"🔹 الخدمات المتاحة:\n"
            f"  • متابعة إنتاجك اليومي والشهري.\n"
            f"  • عرض أرباحك ومستحقاتك.\n"
            f"  • رابط دخول مباشر ومؤمن لتسجيل الإنتاج عبر الويب."
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
    elif profile.entity_type == 'admin':
        return handle_admin_action(profile, text, base_url)

    return {'status': 'unknown_action'}


# ─────────────────────────────────────────────────────────────
# Handlers: Login & Role Menus
# ─────────────────────────────────────────────────────────────
def handle_contact_login(profile: TelegramProfile, phone: str, base_url: str) -> dict:
    """Validates contact phone number and binds worker to TelegramProfile."""
    worker = find_worker_by_phone(phone)

    if not worker:
        msg = (
            f"⚠️ عذراً، رقم الهاتف <code>{phone}</code> غير مسجل في نظام المصنع.\n\n"
            f"يرجى التواصل مع إدارة المصنع لإضافة رقمك في سجلات العمال."
        )
        TelegramBot.send_message(profile.chat_id, msg, reply_markup=get_login_keyboard())
        return {'status': 'phone_not_found'}

    profile.phone = normalize_phone(phone)
    profile.entity_type = 'worker'
    profile.entity_id = worker.pk
    profile.is_authenticated = True
    profile.save()

    welcome_msg = (
        f"✅ <b>تم التحقق بنجاح!</b>\n\n"
        f"مرحباً بك يا <b>{worker.name}</b> (عامل إنتاج).\n"
        f"يمكنك الآن استخدام القائمة أدناه لمتابعة إنتاجك أو الدخول لتسجيل إنتاج جديد."
    )
    TelegramBot.send_message(profile.chat_id, welcome_msg, reply_markup=get_worker_keyboard())
    return {'status': 'authenticated', 'entity_type': 'worker', 'name': worker.name}


def handle_start_command(profile: TelegramProfile, text: str, base_url: str) -> dict:
    """Handles /start command with auto-routing and deep-link parameters."""
    parts = text.strip().split(maxsplit=1)
    param = parts[1].strip() if len(parts) > 1 else ''

    if param:
        # Check if param is w_<id> or worker_<id> or integer pk or phone
        worker = None
        if param.startswith('w_') or param.startswith('worker_'):
            w_id = param.split('_', 1)[1]
            if w_id.isdigit():
                worker = Worker.objects.filter(pk=int(w_id), is_active=True).first()
        elif param.isdigit():
            if len(param) <= 6:
                worker = Worker.objects.filter(pk=int(param), is_active=True).first()
            else:
                worker = find_worker_by_phone(param)
        else:
            worker = find_worker_by_phone(param)

        if worker:
            profile.phone = normalize_phone(worker.phone) if worker.phone else ''
            profile.entity_type = 'worker'
            profile.entity_id = worker.pk
            profile.is_authenticated = True
            profile.save()

            welcome_msg = (
                f"✅ <b>تم الربط والتحقق بنجاح!</b>\n\n"
                f"مرحباً بك يا <b>{worker.name}</b> (عامل إنتاج).\n"
                f"يمكنك الآن استخدام القائمة أدناه لمتابعة إنتاجك أو الدخول لتسجيل إنتاج جديد."
            )
            TelegramBot.send_message(profile.chat_id, welcome_msg, reply_markup=get_worker_keyboard())
            return {'status': 'authenticated_via_start_param', 'worker_id': worker.pk}

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

    # Not logged in
    welcome_text = (
        f"🏭 <b>مرحباً بك في نظام {FACTORY_INFO['name']}</b>\n"
        f"نظام متابعة الإنتاج للعمال.\n\n"
        f"اضغط على زر <b>'📱 تسجيل الدخول عبر رقم الهاتف'</b> بالأسفل لبدء الاستخدام."
    )
    TelegramBot.send_message(profile.chat_id, welcome_text, reply_markup=get_login_keyboard())
    return {'status': 'start_prompt'}


# ─────────────────────────────────────────────────────────────
# Worker Service Actions
# ─────────────────────────────────────────────────────────────
def handle_worker_action(profile: TelegramProfile, text: str, base_url: str) -> dict:
    worker = Worker.objects.filter(pk=profile.entity_id, is_active=True).first()
    if not worker:
        profile.is_authenticated = False
        profile.save()
        TelegramBot.send_message(profile.chat_id, "⚠️ تم إيقاف الحساب أو حذفه.", reply_markup=get_login_keyboard())
        return {'status': 'worker_not_found'}

    today = timezone.localdate()
    t_low = text.lower()

    # ── Today's Production ──
    if text == '📅 إنتاجي اليوم' or t_low in ('/today', 'today'):
        today_entries = ProductionEntry.objects.filter(
            worker=worker, production_date=today, is_cancelled=False
        ).select_related('variant__product_model', 'variant__color', 'variant__size', 'stage')
        today_qty = today_entries.aggregate(q=Sum('quantity'))['q'] or 0
        today_val = today_entries.aggregate(v=Sum('total_amount'))['v'] or 0

        lines = [f"📅 <b>إنتاجك اليوم ({today}):</b>\n"]
        lines.append(f"  • إجمالي القطع: <b>{today_qty:,}</b> قطعة")
        lines.append(f"  • إجمالي المستحق: <b>{today_val:,.2f} ج.م</b>\n")

        if today_entries.exists():
            lines.append("📋 <b>تفاصيل سجلات اليوم:</b>")
            for e in today_entries[:10]:
                lines.append(
                    f"• {e.variant.product_model.code} | {e.variant.color.name}/{e.variant.size.name} "
                    f"| {e.stage.name}: <b>{e.quantity:,}</b> قطعة"
                )
        else:
            lines.append("لا توجد سجلات إنتاج اليوم حتى الآن.")

        TelegramBot.send_message(profile.chat_id, "\n".join(lines), reply_markup=get_worker_keyboard())
        return {'status': 'worker_today_sent'}

    # ── This Month's Production ──
    if text == '📊 إنتاج هذا الشهر' or t_low in ('/month', 'month'):
        start_date, end_date = get_current_month_date_range()
        summary = get_worker_earnings(worker, start_date, end_date)
        history = get_worker_production_history(worker, start_date, end_date)

        # Group by model/color/size/stage
        breakdown = _build_grouped_summary(history)

        lines = [f"📊 <b>إنتاج هذا الشهر — {worker.name}</b>\n"]
        lines.append(f"  • إجمالي القطع: <b>{summary['total_qty']:,}</b> قطعة")
        lines.append(f"  • إجمالي المستحق: <b>{summary['total_amount']:,.2f} ج.م</b>")
        lines.append(f"  • عدد السجلات: <b>{summary['entry_count']:,}</b>\n")

        if breakdown:
            lines.append("📦 <b>تفاصيل حسب الموديل والمرحلة:</b>")
            for model_code, sizes in breakdown.items():
                lines.append(f"\n🔹 <b>موديل: {model_code}</b>")
                for size_key, stages in sizes.items():
                    lines.append(f"  • {size_key}")
                    for stage_name, qty in stages.items():
                        lines.append(f"    - {stage_name}: <b>{qty:,}</b> قطعة")

        TelegramBot.send_message(profile.chat_id, "\n".join(lines), reply_markup=get_worker_keyboard())
        return {'status': 'worker_month_sent'}

    # ── Last Month's Production ──
    if text == '📊 إنتاج الشهر الماضي' or t_low in ('/lastmonth',):
        ly, lm = _last_month()
        start_date, end_date = _get_month_range(ly, lm)
        summary = get_worker_earnings(worker, start_date, end_date)
        history = get_worker_production_history(worker, start_date, end_date)
        breakdown = _build_grouped_summary(history)

        month_label = f"{ARABIC_MONTHS[lm]} {ly}"
        lines = [f"📊 <b>إنتاج الشهر الماضي ({month_label}) — {worker.name}</b>\n"]
        lines.append(f"  • إجمالي القطع: <b>{summary['total_qty']:,}</b> قطعة")
        lines.append(f"  • إجمالي المستحق: <b>{summary['total_amount']:,.2f} ج.م</b>")
        lines.append(f"  • عدد السجلات: <b>{summary['entry_count']:,}</b>\n")

        if breakdown:
            lines.append("📦 <b>تفاصيل حسب الموديل والمرحلة:</b>")
            for model_code, sizes in breakdown.items():
                lines.append(f"\n🔹 <b>موديل: {model_code}</b>")
                for size_key, stages in sizes.items():
                    lines.append(f"  • {size_key}")
                    for stage_name, qty in stages.items():
                        lines.append(f"    - {stage_name}: <b>{qty:,}</b> قطعة")

        TelegramBot.send_message(profile.chat_id, "\n".join(lines), reply_markup=get_worker_keyboard())
        return {'status': 'worker_last_month_sent'}

    # ── Open Dashboard (Magic Link) ──
    if text in ('🌐 فتح لوحة التحكم',) or t_low in ('/web', 'web', '/link', 'link', '/dashboard', 'dashboard'):
        token_obj = MagicLoginToken.create_token('worker', worker.pk, worker.name, expiry_minutes=60)
        login_url = f"{base_url.rstrip('/')}/workers/telegram-login/{token_obj.token}/"
        msg = (
            f"👷 <b>مرحباً {worker.name}</b>\n\n"
            f"🔗 <b>رابط الدخول المباشر إلى لوحة متابعة إنتاجك:</b>\n"
            f"<a href='{login_url}'>👉 اضغط هنا لفتح لوحة التحكم</a>\n\n"
            f"⏱️ <i>هذا الرابط صالح للاستخدام لمرة واحدة فقط ومدة الجلسة ساعة واحدة.</i>"
        )
        TelegramBot.send_message(profile.chat_id, msg, reply_markup=get_worker_keyboard())
        return {'status': 'worker_dashboard_link_sent'}

    # ── Start Production / QR Scan ──
    if text in ('📱 تسجيل إنتاج جديد',) or t_low in ('/production', 'production', '/qr', 'qr', '/scan', 'scan'):
        token_obj = MagicLoginToken.create_token('worker', worker.pk, worker.name, expiry_minutes=60)
        entry_url = f"{base_url.rstrip('/')}/workers/telegram-login/{token_obj.token}/?next=/production/entry/"
        msg = (
            f"📱 <b>تسجيل إنتاج جديد</b>\n\n"
            f"1️⃣ <b>مسح QR للصنف:</b> امسح كود QR المطبوع على أمر الشغل أو الصنف بكاميرا هاتفك.\n"
            f"2️⃣ <b>أو الدخول المباشر:</b> اضغط على الرابط أدناه لتسجيل الدخول والبدء:\n\n"
            f"<a href='{entry_url}'>👉 رابط تسجيل الإنتاج</a>\n\n"
            f"⏱️ <i>الرابط صالح للاستخدام لمرة واحدة ومدة الجلسة ساعة.</i>"
        )
        TelegramBot.send_message(profile.chat_id, msg, reply_markup=get_worker_keyboard())
        return {'status': 'worker_production_link_sent'}

    # Fallback: resend menu
    TelegramBot.send_message(
        profile.chat_id,
        f"👷 <b>{worker.name}</b> — اختر من القائمة:",
        reply_markup=get_worker_keyboard()
    )
    return {'status': 'worker_menu_resent'}


def _build_grouped_summary(history) -> dict:
    """
    Build a nested dict: model_code -> 'color/size' -> stage_name -> quantity
    from a queryset of ProductionEntry.
    """
    grouped = {}
    for e in history:
        model_code = e.variant.product_model.code
        size_key = f"{e.variant.color.name} / {e.variant.size.name}"
        stage_name = e.stage.name
        grouped.setdefault(model_code, {}).setdefault(size_key, {})
        grouped[model_code][size_key][stage_name] = (
            grouped[model_code][size_key].get(stage_name, 0) + e.quantity
        )
    return grouped


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
        from catalog.models import ProductModel
        entries = ProductionEntry.objects.filter(
            production_date__gte=start_date, production_date__lte=end_date, is_cancelled=False
        )
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
        entries = ProductionEntry.objects.filter(
            production_date__gte=start_date, production_date__lte=end_date, is_cancelled=False
        )
        total_qty = entries.aggregate(q=Sum('quantity'))['q'] or 0
        total_val = entries.aggregate(v=Sum('total_amount'))['v'] or 0

        pdf = FactoryPDFReport(
            title='تقرير متابعة وسجل الإنتاج العام للمصنع (مرتب ومبوب)',
            subtitle=f'الفترة من {start_date} إلى {end_date}'
        )
        pdf.add_header(filters_dict={'الفترة': f'{start_date} إلى {end_date}'})
        pdf.add_kpis([
            ('إجمالي القطع', f"{total_qty:,} قطعة"),
            ('إجمالي القيمة', f"{total_val:,.2f} ج.م"),
            ('عدد السجلات', f"{entries.count():,} سجل"),
        ])

        # Stage Breakdown Table (Sorted by total quantity descending)
        stage_stats = entries.values('stage__name').annotate(
            total_qty=Sum('quantity'), total_amount=Sum('total_amount')
        ).order_by('-total_qty')
        if stage_stats.exists():
            pdf.add_section_title('ملخص الإنتاج وتكلفة التشغيل حسب المراحل (مرتب حسب الكمية)')
            stage_rows = []
            for s in stage_stats:
                stage_rows.append([
                    s['stage__name'],
                    f"{s['total_qty']:,} قطعة",
                    f"{s['total_amount']:,.2f} ج.م",
                ])
            pdf.add_table(
                headers=['مرحلة الإنتاج', 'إجمالي الكمية المنجزة', 'إجمالي القيمة / التكلفة'],
                rows=stage_rows,
                col_widths=[220, 155, 160],
                right_align_cols=[0]
            )

        # Worker Breakdown Table (Sorted by total earnings descending)
        worker_stats = entries.values('worker__name').annotate(
            total_qty=Sum('quantity'), total_amount=Sum('total_amount')
        ).order_by('-total_amount')
        if worker_stats.exists():
            pdf.add_section_title('ملخص إنتاج ومستحقات العمال (مرتب حسب الأعلى استحقاقاً)')
            w_rows = []
            for rank, w in enumerate(worker_stats[:20], 1):
                w_rows.append([
                    f"{rank}. {w['worker__name']}",
                    f"{w['total_qty']:,} قطعة",
                    f"{w['total_amount']:,.2f} ج.م",
                ])
            pdf.add_table(
                headers=['العامل', 'الكمية المنتجة', 'إجمالي المستحقات'],
                rows=w_rows,
                col_widths=[235, 150, 150],
                right_align_cols=[0]
            )

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
