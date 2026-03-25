from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [

    path('admin/', admin.site.urls),

    path('accounts/', include('accounts.urls')),
    path('api/accounts/', include('accounts.api_urls')),

    path('policy/', include('policy.urls')),

    path('premiums/', include('premiums.urls')),

    path('claims/', include('claims.urls')),
    path('reports/', include('reports.urls')),

    path('', lambda request: redirect('accounts:login'), name='home'),

]
from django.conf import settings
from django.conf.urls.static import static

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)