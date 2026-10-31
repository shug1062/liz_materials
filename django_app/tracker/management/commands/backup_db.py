import shutil
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone


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
        dest.close()
        self.stdout.write(self.style.SUCCESS(f"Backup written: {target}"))

        if settings.BACKUP_COPY_DIR:
            copy_dir = Path(settings.BACKUP_COPY_DIR)
            copy_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, copy_dir / target.name)
            self.stdout.write(f"Copied to {copy_dir}")

        # Names sort by timestamp, so this never depends on file modified-times.
        backups = sorted(backup_dir.glob("studio-*.sqlite3"))
        for old in backups[: -settings.BACKUP_KEEP]:
            old.unlink()
