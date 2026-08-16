from django.urls import path
from . import views

app_name = 'catalog'

urlpatterns = [
    # Settings (at /settings/)
    path('settings/', views.SettingsIndexView.as_view(), name='settings_index'),
    path('settings/colors/', views.ColorListView.as_view(), name='color_list'),
    path('settings/colors/<int:pk>/edit/', views.ColorEditView.as_view(), name='color_edit'),
    path('settings/colors/<int:pk>/toggle/', views.color_toggle, name='color_toggle'),
    path('settings/sizes/', views.SizeListView.as_view(), name='size_list'),
    path('settings/sizes/<int:pk>/toggle/', views.size_toggle, name='size_toggle'),
    path('settings/stages/', views.StageListView.as_view(), name='stage_list'),
    path('settings/stages/<int:pk>/toggle/', views.stage_toggle, name='stage_toggle'),

    # Clients (at /clients/)
    path('clients/', views.ClientListView.as_view(), name='client_list'),
    path('clients/create/', views.ClientCreateView.as_view(), name='client_create'),
    path('clients/<int:pk>/', views.ClientDetailView.as_view(), name='client_detail'),
    path('clients/<int:pk>/edit/', views.ClientEditView.as_view(), name='client_edit'),
    path('clients/<int:pk>/toggle/', views.client_toggle, name='client_toggle'),

    # Product Models (at /models/)
    path('models/', views.ModelListView.as_view(), name='model_list'),
    path('models/create/step1/', views.ModelWizardStep1.as_view(), name='model_wizard_step1'),
    path('models/create/step2/', views.ModelWizardStep2.as_view(), name='model_wizard_step2'),
    path('models/create/step3/', views.ModelWizardStep3.as_view(), name='model_wizard_step3'),
    path('models/create/step4/', views.ModelWizardStep4.as_view(), name='model_wizard_step4'),
    path('models/create/review/', views.ModelWizardReview.as_view(), name='model_wizard_review'),
    path('models/create/generate/', views.ModelWizardGenerate.as_view(), name='model_wizard_generate'),
    path('models/<int:pk>/', views.ModelDetailView.as_view(), name='model_detail'),
    path('models/<int:pk>/toggle/', views.model_toggle, name='model_toggle'),
    path('models/<int:pk>/qr-sheet/', views.ModelQRSheetView.as_view(), name='model_qr_sheet'),
    path('models/variants/<int:pk>/update/', views.VariantUpdateView.as_view(), name='variant_update'),
    path('models/variants/<int:pk>/qr/', views.VariantQRImageView.as_view(), name='variant_qr_image'),
    path('models/variants/<int:pk>/qr-card/', views.VariantQRCardView.as_view(), name='variant_qr_card'),
]
