from django.apps import AppConfig


class AiFeaturesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai_features'
    verbose_name = 'AI Features'
    
    def ready(self):
        import ai_features.signals  # noqa