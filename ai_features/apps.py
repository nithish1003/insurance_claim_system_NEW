from django.apps import AppConfig


class AiFeaturesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_features'
    verbose_name = 'AI Features'
    
    def ready(self):
        import ai_features.signals  # noqa
        # 🚀 Startup Warm Load removed to prevent PaddleOCR connectivity checks during boot
        # Engines will now lazy-load on first use (KYC/Claims)