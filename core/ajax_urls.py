"""Central AJAX URL router — all /ajax/ endpoints."""
from django.urls import path
from production.views import (
    ajax_models_by_client, ajax_variants_by_model,
    ajax_stages_by_variant, ajax_workers_by_stage, ajax_price_for_stage
)

app_name = 'ajax'

urlpatterns = [
    path('models-by-client/', ajax_models_by_client, name='models_by_client'),
    path('variants-by-model/', ajax_variants_by_model, name='variants_by_model'),
    path('stages-by-variant/', ajax_stages_by_variant, name='stages_by_variant'),
    path('workers-by-stage/', ajax_workers_by_stage, name='workers_by_stage'),
    path('price-for-stage/', ajax_price_for_stage, name='price_for_stage'),
]
