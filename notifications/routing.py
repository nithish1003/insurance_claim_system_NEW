from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # 📡 Personal Notification Hub
    re_path(r'ws/notifications/$', consumers.NotificationConsumer.as_asgi()),
]
