import os
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.conf import settings
from django.conf.urls.static import static

from django.views.generic import RedirectView, TemplateView
from django.http import HttpResponse

def robots_txt_view(request):
    """Serve robots.txt dynamically from the static directory."""
    robots_path = os.path.join(settings.BASE_DIR, 'static', 'robots.txt')
    try:
        with open(robots_path, 'r') as f:
            return HttpResponse(f.read(), content_type="text/plain")
    except FileNotFoundError:
        return HttpResponse("User-agent: *\nAllow: /\n", content_type="text/plain")

def google_verification_view(request):
    """Serve the Google verification HTML file."""
    file_path = os.path.join(settings.BASE_DIR, 'google8f788afc0a4fb706.html')
    try:
        with open(file_path, 'r') as f:
            return HttpResponse(f.read(), content_type="text/html")
    except FileNotFoundError:
        return HttpResponse("Verification file not found.", status=404)

from django.contrib.sitemaps.views import sitemap
from .sitemaps import StaticViewSitemap

sitemaps = {
    'static': StaticViewSitemap,
}

urlpatterns = [
    path('google8f788afc0a4fb706.html', google_verification_view),
    path('robots.txt', robots_txt_view),
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
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
