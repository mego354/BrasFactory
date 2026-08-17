from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve

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
    path('notifications/', include('notifications.urls', namespace='notifications')),
    path('ajax/', include('core.ajax_urls', namespace='ajax')),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if not settings.DEBUG:
    urlpatterns += [
        re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_ROOT}),
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]

