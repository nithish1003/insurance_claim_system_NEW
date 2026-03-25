from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .api_views import CustomTokenObtainPairView, RegisterView, CurrentUserView

app_name = "api_accounts"

urlpatterns = [
    path('login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('register/', RegisterView.as_view(), name='api_register'),
    path('me/', CurrentUserView.as_view(), name='api_current_user'),
]
