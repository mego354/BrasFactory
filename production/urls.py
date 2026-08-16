from django.urls import path
from . import views

app_name = 'production'

urlpatterns = [
    path('', views.DashboardView.as_view(), name='dashboard'),
    path('entry/', views.ProductionEntryView.as_view(), name='entry'),
    path('entry/<int:pk>/cancel/', views.CancelEntryView.as_view(), name='cancel_entry'),
]
