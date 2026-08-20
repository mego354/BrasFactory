"""
Notification & Telegram Models:
- TelegramProfile: Mapping between Telegram Chat ID and Factory Workers/Admins.
- MagicLoginToken: Secure one-time login links for Telegram users (1-hour, single-use).
"""
import secrets
from django.db import models
from django.utils import timezone


class TelegramProfile(models.Model):
    chat_id = models.CharField(max_length=64, unique=True, verbose_name='معرف المحادثة Chat ID')
    phone = models.CharField(max_length=25, blank=True, verbose_name='رقم الهاتف المسجل')
    username = models.CharField(max_length=100, blank=True, verbose_name='اسم المستخدم')
    first_name = models.CharField(max_length=100, blank=True, verbose_name='الاسم')
    entity_type = models.CharField(
        max_length=10,
        choices=[('worker', 'عامل'), ('admin', 'إدارة')],
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
    def create_token(cls, entity_type: str, entity_id: int, name: str, expiry_minutes: int = 60):
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
