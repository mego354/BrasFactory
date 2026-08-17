from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('telegram/webhook/', views.TelegramWebhookView.as_view(), name='telegram_webhook'),
    path('magic-login/<str:token>/', views.MagicLoginView.as_view(), name='magic_login'),
]
