"""
Notification & Telegram Models:
- OTPRecord: Hash-based OTP storage.
- TelegramProfile: Mapping between Telegram Chat ID and Factory Entities (Client, Worker, Admin).
- MagicLoginToken: Secure one-time login links for Telegram users.
"""
import hashlib
import secrets
from django.db import models
from django.utils import timezone


class OTPRecord(models.Model):
    phone = models.CharField(max_length=20, verbose_name='رقم الهاتف')
    otp_hash = models.CharField(max_length=64, verbose_name='OTP (مُجزَّأ)')
    entity_type = models.CharField(
        max_length=10,
        choices=[('client', 'عميل'), ('worker', 'عامل')],
        verbose_name='نوع الكيان'
    )
    entity_id = models.PositiveIntegerField(verbose_name='معرف الكيان')
    expires_at = models.DateTimeField(verbose_name='ينتهي في')
    is_used = models.BooleanField(default=False, verbose_name='مستخدم')
    attempt_count = models.PositiveIntegerField(default=0, verbose_name='عدد المحاولات')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'سجل OTP'
        verbose_name_plural = 'سجلات OTP'
        indexes = [
            models.Index(fields=['phone', 'is_used', 'expires_at']),
        ]

    def __str__(self):
        return f"OTP for {self.phone} ({self.entity_type}:{self.entity_id})"

    @staticmethod
    def hash_otp(otp: str) -> str:
        return hashlib.sha256(otp.encode()).hexdigest()

    def verify(self, otp: str) -> bool:
        return self.otp_hash == self.hash_otp(otp)

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_locked(self):
        from django.conf import settings
        return self.attempt_count >= getattr(settings, 'OTP_MAX_ATTEMPTS', 3)


class TelegramProfile(models.Model):
    chat_id = models.CharField(max_length=64, unique=True, verbose_name='معرف المحادثة Chat ID')
    phone = models.CharField(max_length=25, blank=True, verbose_name='رقم الهاتف المسجل')
    username = models.CharField(max_length=100, blank=True, verbose_name='اسم المستخدم')
    first_name = models.CharField(max_length=100, blank=True, verbose_name='الاسم')
    entity_type = models.CharField(
        max_length=10,
        choices=[('client', 'عميل'), ('worker', 'عامل'), ('admin', 'إدارة')],
        blank=True,
        verbose_name='نوع الحساب'
    )
    entity_id = models.PositiveIntegerField(null=True, blank=True, verbose_name='معرف الكيان')
    is_authenticated = models.BooleanField(default=False, verbose_name='موثق')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'ملف تليجرام'
        verbose_name_plural = 'ملفات تليجرام'

    def __str__(self):
        return f"{self.first_name} ({self.chat_id}) - {self.entity_type}:{self.entity_id}"


class MagicLoginToken(models.Model):
    token = models.CharField(max_length=64, unique=True, verbose_name='رمز الدخول')
    entity_type = models.CharField(max_length=10, verbose_name='نوع الكيان')
    entity_id = models.PositiveIntegerField(verbose_name='معرف الكيان')
    name = models.CharField(max_length=100, verbose_name='الاسم')
    expires_at = models.DateTimeField(verbose_name='ينتهي في')
    is_used = models.BooleanField(default=False, verbose_name='مستخدم')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'رمز دخول سريع'
        verbose_name_plural = 'رموز الدخول السريع'

    @classmethod
    def create_token(cls, entity_type: str, entity_id: int, name: str, expiry_minutes: int = 15):
        token_str = secrets.token_urlsafe(32)
        expires = timezone.now() + timezone.timedelta(minutes=expiry_minutes)
        return cls.objects.create(
            token=token_str,
            entity_type=entity_type,
            entity_id=entity_id,
            name=name,
            expires_at=expires,
        )

    @property
    def is_valid(self):
        return not self.is_used and timezone.now() <= self.expires_at
