import shutil
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Move the live database out of the app folder (which may be synced by OneDrive) into DATA_DIR."
    requires_system_checks = []

    def handle(self, **options):
        source, target = Path(settings.LEGACY_DATA_DIR), Path(settings.DATA_DIR)
        old_db, new_db = source / "studio.sqlite3", target / "studio.sqlite3"
        if source.resolve() == target.resolve() or not old_db.exists():
            return
        if new_db.exists():
            self.stdout.write(self.style.WARNING(
                f"{old_db} is not being used – the live database is {new_db}. Delete the old one once you're sure."
            ))
            return

        target.mkdir(parents=True, exist_ok=True)
        # The backup API gives a consistent copy, including anything still in the old -wal file.
        src = sqlite3.connect(old_db)
        dest = sqlite3.connect(new_db)
        with dest:
            src.backup(dest)
        dest.close()
        src.close()
        if (source / "secret_key.txt").exists():
            shutil.copyfile(source / "secret_key.txt", target / "secret_key.txt")
        if (source / "backups").is_dir():
            shutil.copytree(source / "backups", target / "backups", dirs_exist_ok=True)
        old_db.rename(old_db.with_name("studio.sqlite3.moved"))
        self.stdout.write(self.style.SUCCESS(f"Moved the live database to {new_db} (outside OneDrive)."))
