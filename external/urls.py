from django.urls import path
from . import views

app_name = 'external'

urlpatterns = [
    path('worker/', views.ExternalWorkerDashboardView.as_view(), name='worker_dashboard'),
    path('logout/', views.ExternalLogoutView.as_view(), name='logout'),
]
