"""
OTP Record model — never stores raw OTP, only SHA-256 hash.
"""
import hashlib
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
