from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('', views.ReportIndexView.as_view(), name='index'),
    path('by-model/', views.ReportByModelView.as_view(), name='by_model'),
    path('by-worker/', views.ReportByWorkerView.as_view(), name='by_worker'),
    path('by-client/', views.ReportByClientView.as_view(), name='by_client'),
    path('by-stage/', views.ReportByStageView.as_view(), name='by_stage'),
]
