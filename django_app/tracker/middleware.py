from django.contrib.auth import get_user_model, login


import logging
import sqlite3
import threading

from django.conf import settings
from django.contrib import messages
from django.core.management import call_command
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import StudioSettings

logger = logging.getLogger(__name__)
_daily_backup_lock = threading.Lock()
_backup_checked_on = None


class AutoLoginMiddleware:
    """Signs every visitor in as the studio owner, for a trusted home network."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.user.is_authenticated:
            User = get_user_model()
            user = User.objects.filter(is_superuser=True, is_active=True).order_by("pk").first()
            if user is None:
                user = User.objects.create_superuser("studio", password=None)
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return self.get_response(request)


def login_settings(request):
    return {"require_login": settings.REQUIRE_LOGIN}


class DailyBackupMiddleware:
    """Copies the database on the first app request each day when a destination is configured."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        global _backup_checked_on
        today = timezone.localdate()
        # Cheap check first: after the first request of the day, no database query or lock is needed.
        if _backup_checked_on != today and request.user.is_authenticated and not request.path.startswith("/static/"):
            with _daily_backup_lock:
                if _backup_checked_on != today:
                    _backup_checked_on = today
                    self._backup_if_due(request, today)
        return self.get_response(request)

    @staticmethod
    def _backup_if_due(request, today):
        studio_settings = StudioSettings.objects.filter(pk=1).first()
        destination = (
            studio_settings.backup_directory
            if studio_settings and studio_settings.backup_directory is not None
            else settings.BACKUP_COPY_DIR
        )
        if destination and (studio_settings is None or studio_settings.last_backup_date != today):
            try:
                call_command("backup_db")
            except (OSError, sqlite3.Error) as error:
                logger.exception("Daily studio backup failed.")
                messages.error(request, f"Daily backup failed: {error}")


@receiver(post_save, sender=StudioSettings)
def _recheck_backup_after_settings_change(update_fields=None, **kwargs):
    global _backup_checked_on
    if update_fields != frozenset({"last_backup_date"}):
        _backup_checked_on = None
