from django.urls import path
from . import views

app_name = 'workers'

urlpatterns = [
    path('', views.WorkerListView.as_view(), name='list'),
    path('create/', views.WorkerCreateView.as_view(), name='create'),
    path('<int:pk>/', views.WorkerDetailView.as_view(), name='detail'),
    path('<int:pk>/edit/', views.WorkerEditView.as_view(), name='edit'),
    path('<int:pk>/toggle/', views.worker_toggle, name='toggle'),
    path('<int:pk>/telegram-link/', views.GenerateWorkerTelegramLinkView.as_view(), name='telegram_link'),
    path('portal-login/<str:token>/', views.WorkerTelegramDirectLoginView.as_view(), name='telegram_direct_login'),
    path('telegram-login/<str:token>/', views.WorkerTelegramDirectLoginView.as_view(), name='telegram_login_alias'),
]

