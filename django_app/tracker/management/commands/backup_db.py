import shutil
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from tracker.models import StudioSettings


class Command(BaseCommand):
    help = "Make a consistent copy of the database (safe while the app is running)."

    def handle(self, **options):
        backup_dir = Path(settings.BACKUP_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)
        target = backup_dir / f"studio-{timezone.localtime():%Y%m%d-%H%M%S}.sqlite3"

        connection.ensure_connection()
        dest = sqlite3.connect(target)
        with dest:
            connection.connection.backup(dest)
        # A plain single-file copy: WAL mode would make OneDrive see side files whenever it's opened.
        dest.execute("PRAGMA journal_mode=DELETE")
        dest.close()
        self.stdout.write(self.style.SUCCESS(f"Backup written: {target}"))

        studio_settings = StudioSettings.objects.filter(pk=1).first()
        configured_dir = (
            studio_settings.backup_directory
            if studio_settings and studio_settings.backup_directory is not None
            else settings.BACKUP_COPY_DIR
        )
        if configured_dir:
            copy_dir = Path(configured_dir).expanduser()
            copy_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, copy_dir / target.name)
            self.stdout.write(f"Copied to {copy_dir}")
            if studio_settings is None:
                studio_settings = StudioSettings.objects.create(pk=1)
            studio_settings.last_backup_date = timezone.localdate()
            studio_settings.save(update_fields=["last_backup_date"])

        # Names sort by timestamp, so this never depends on file modified-times.
        backups = sorted(backup_dir.glob("studio-*.sqlite3"))
        for old in backups[: -settings.BACKUP_KEEP]:
            old.unlink()
