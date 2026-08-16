from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/', include('accounts.urls', namespace='accounts')),

    # Production dashboard & entry
    path('', include('production.urls', namespace='production')),

    # Catalog apps: /clients/, /models/, /settings/
    path('', include('catalog.urls', namespace='catalog')),

    # Other apps
    path('workers/', include('workers.urls', namespace='workers')),
    path('reports/', include('reports.urls', namespace='reports')),
    path('external/', include('external.urls', namespace='external')),
    path('ajax/', include('core.ajax_urls', namespace='ajax')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
