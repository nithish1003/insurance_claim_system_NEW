import os
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static

from django.views.generic import RedirectView, TemplateView

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── ACCOUNTS ──
    path('accounts/', include(('accounts.urls', 'accounts'), namespace='accounts')),
    path('api/accounts/', include(('accounts.api_urls', 'api_accounts'), namespace='api_accounts')),

    # ── CLAIMS ──
    path('claim/', include(('claims.urls', 'claim'), namespace='claim')),

    # ── POLICY & OTHERS ──
    path('policy/', include(('policy.urls', 'policy'), namespace='policy')),
    path('notifications/', include(('notifications.urls', 'notifications'), namespace='notifications')),
    path('analytics/', include(('analytics.urls', 'analytics'), namespace='analytics')),

    # ── FINANCIALS & REPORTS ──
    path('premiums/', include('premiums.urls')),
    path('reports/', include('reports.urls')),

    # ── LEGACY REDIRECTS ──
    path('login/', RedirectView.as_view(url='/accounts/login/', permanent=True)),
    path('register/', RedirectView.as_view(url='/accounts/register/', permanent=True)),
    path('test/', RedirectView.as_view(url='/claim/test/', permanent=False)),
    # ── HOME ──
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
    path('favicon.ico', RedirectView.as_view(url='/static/images/favicon.svg')),
    path("assistant/", include("assistant.urls")),

    # ── GLOBAL SAFETY REDIRECTS ──
    # Catch-all for common pluralization and redundant "detail/" segments
    path('claims/', RedirectView.as_view(url='/claim/', permanent=False)),
    path('claims/detail/<path:extra>/', RedirectView.as_view(url='/claim/%(extra)s/', permanent=False)),
    path('claim/detail/<path:extra>/', RedirectView.as_view(url='/claim/%(extra)s/', permanent=False)),
    path('claims/<path:extra>/', RedirectView.as_view(url='/claim/%(extra)s/', permanent=False)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=os.path.join(settings.BASE_DIR, 'static'))
