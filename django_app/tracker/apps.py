from django.apps import AppConfig


class TrackerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tracker"
    verbose_name = "Studio tracker"

    def ready(self):
        from . import silver  # noqa: F401  (connects the silver re-costing signals)
