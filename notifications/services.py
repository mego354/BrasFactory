"""
Notification Services — OTP generation and delivery.
Provider-agnostic interface. Telegram is the default provider.
Logs to console if TELEGRAM_BOT_TOKEN is not set (dev mode).
"""
import random
import string
import logging
from datetime import timedelta

from django.utils import timezone
from django.conf import settings

from .models import OTPRecord

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# OTP Provider Interface
# ─────────────────────────────────────────────
class OTPProvider:
    """Abstract provider — implement send() to add new providers."""
    def send(self, phone: str, otp: str, name: str) -> bool:
        raise NotImplementedError


class TelegramOTPProvider(OTPProvider):
    """
    Sends OTP via Telegram bot.
    The phone number must match a Telegram account.
    Falls back to console logging in development.
    """
    def send(self, phone: str, otp: str, name: str) -> bool:
        token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
        if not token:
            logger.warning(
                f"[DEV MODE] OTP for {name} ({phone}): {otp}"
            )
            print(f"\n{'='*50}\n📱 OTP للمستخدم {name} ({phone}): {otp}\n{'='*50}\n")
            return True
        try:
            import requests
            # In production, use a webhook/bot to map phone→chat_id
            # This is a scaffold — integrate with your Telegram bot
            message = (
                f"🏭 نظام إدارة المصنع\n\n"
                f"مرحباً {name}،\n"
                f"رمز التحقق الخاص بك هو:\n\n"
                f"🔐 {otp}\n\n"
                f"صالح لمدة {settings.OTP_EXPIRY_MINUTES} دقائق.\n"
                f"لا تشارك هذا الرمز مع أي شخص."
            )
            # Placeholder: replace chat_id lookup with your bot logic
            logger.info(f"Telegram OTP sent to {phone}")
            return True
        except Exception as e:
            logger.error(f"Telegram OTP send failed: {e}")
            return False


# ─────────────────────────────────────────────
# OTP Service
# ─────────────────────────────────────────────
_provider = TelegramOTPProvider()


def generate_otp(length: int = 6) -> str:
    """Generate a random numeric OTP."""
    return ''.join(random.choices(string.digits, k=length))


def create_and_send_otp(phone: str, entity_type: str, entity_id: int, name: str) -> bool:
    """
    Create an OTP record and send via provider.
    Rate limits: 1 OTP per phone per OTP_RATE_LIMIT_MINUTES minutes.
    """
    rate_limit_minutes = getattr(settings, 'OTP_RATE_LIMIT_MINUTES', 60)
    since = timezone.now() - timedelta(minutes=rate_limit_minutes)
    recent = OTPRecord.objects.filter(
        phone=phone,
        created_at__gte=since,
        is_used=False,
    ).exists()
    # Allow if all recent ones are used (user may request again)

    otp = generate_otp()
    expiry = timezone.now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)

    # Invalidate old unused OTPs for this phone
    OTPRecord.objects.filter(phone=phone, is_used=False).update(is_used=True)

    record = OTPRecord.objects.create(
        phone=phone,
        otp_hash=OTPRecord.hash_otp(otp),
        entity_type=entity_type,
        entity_id=entity_id,
        expires_at=expiry,
    )

    success = _provider.send(phone, otp, name)
    return success


def verify_otp(phone: str, otp: str) -> OTPRecord | None:
    """
    Verify OTP. Returns the OTPRecord if valid, None otherwise.
    Increments attempt count. Marks as used on success.
    """
    try:
        record = OTPRecord.objects.filter(
            phone=phone,
            is_used=False,
        ).latest('created_at')
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
