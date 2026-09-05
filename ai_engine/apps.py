from django.apps import AppConfig


class AiEngineConfig(AppConfig):
    name = 'ai_engine'

    def ready(self):
        from . import signals  # noqa: F401
