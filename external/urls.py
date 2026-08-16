from django.urls import path
from . import views

app_name = 'external'

urlpatterns = [
    path('', views.OTPRequestView.as_view(), name='otp_request'),
    path('verify/', views.OTPVerifyView.as_view(), name='otp_verify'),
    path('client/', views.ExternalClientDashboardView.as_view(), name='client_dashboard'),
    path('worker/', views.ExternalWorkerDashboardView.as_view(), name='worker_dashboard'),
    path('logout/', views.ExternalLogoutView.as_view(), name='logout'),
]
