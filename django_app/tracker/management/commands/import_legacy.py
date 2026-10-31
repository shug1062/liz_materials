import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tracker.models import (
    Category, ClassOrder, Material, Payment, Project, Purchase, Student, money,
)

PRICING_TYPES = {"fixed": "fixed", "per_kg": "per_gram", "per_kg_item": "per_gram_item"}
# Products renamed when metalclay.co.uk moved to its new shop (Oct 2026).
RENAMED_LINKS = {
    "https://www.metalclay.co.uk/art-clay-silver-clay-7gm-bulk-buy-10pcs/":
        "https://www.metalclay.co.uk/products/class-pack-of-10-art-clay-silver-clay-7gm-new-formula",
}


def dec(value, default="0") -> Decimal:
    # str() first: Decimal(0.1) would keep the float's binary error (0.1000000000000000055...).
    return Decimal(str(value)) if value is not None else Decimal(default)


def parse_dt(value):
    if not value:
        return timezone.now()
    dt = datetime.fromisoformat(str(value).replace("T", " "))
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


class Command(BaseCommand):
    help = "Import data from the old NiceGUI jewelry_business.db (read-only) into this app."

    def add_arguments(self, parser):
        parser.add_argument("legacy_db", type=Path)
        parser.add_argument("--if-empty", action="store_true", help="Skip quietly if this app already has data.")

    def handle(self, legacy_db: Path, if_empty=False, **options):
        if not legacy_db.exists():
            raise CommandError(f"{legacy_db} not found")
        if Student.objects.exists() or Material.objects.exists():
            if if_empty:
                self.stdout.write(f"Found {legacy_db.name}, but this app already has data – not importing it again.")
                return
            raise CommandError("This database already has data – import into a fresh database only.")

        src = sqlite3.connect(f"file:{legacy_db}?mode=ro", uri=True)
        src.row_factory = sqlite3.Row
        rows = lambda table: [dict(r) for r in src.execute(f"SELECT * FROM {table}")]  # noqa: E731
        tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        with transaction.atomic():
            for r in rows("students"):
                Student.objects.create(
                    id=r["id"], name=r["name"], class_name=r.get("class_name") or "",
                    email=r.get("email") or "", phone=r.get("phone") or "", notes=r.get("notes") or "",
                    is_sales_channel=bool(r.get("is_sales_channel")), created_at=parse_dt(r.get("created_at")),
                )

            if "class_order" in tables:
                for r in rows("class_order"):
                    ClassOrder.objects.create(class_name=r["class_name"], sort_order=r["sort_order"])

            category_order = {}
            if "category_order" in tables:
                category_order = {r["category_name"]: r["sort_order"] for r in rows("category_order")}
            material_order = {}
            if "material_order" in tables:
                material_order = {r["material_id"]: r["sort_order"] for r in rows("material_order")}

            categories = {}
            for r in rows("materials"):
                cat_name = (r.get("category") or "").strip()
                category = None
                if cat_name:
                    key = cat_name.lower()
                    if key not in categories:
                        categories[key] = Category.objects.create(
                            name=cat_name, sort_order=category_order.get(cat_name, 1000)
                        )
                    category = categories[key]
                Material.objects.create(
                    id=r["id"], name=r["name"], category=category, unit_type=r.get("unit_type") or "item",
                    pricing_type=PRICING_TYPES.get(r.get("pricing_type") or "fixed", "fixed"),
                    base_price=dec(r["base_price"]).quantize(Decimal("0.0001")),
                    pack_quantity=dec(r.get("pack_quantity"), "1") or Decimal("1"),
                    weight_per_unit=dec(r["weight_per_unit"]).quantize(Decimal("0.0001")) if r.get("weight_per_unit") else None,
                    markup_percentage=dec(r.get("markup_percentage")).quantize(Decimal("0.01")),
                    supplier=r.get("supplier") or "",
                    supplier_url=RENAMED_LINKS.get(r.get("supplier_url") or "", r.get("supplier_url") or ""),
                    is_active=bool(r.get("is_active", 1)), sort_order=material_order.get(r["id"], 1000),
                    notes=r.get("notes") or "",
                )

            for r in rows("projects"):
                Project.objects.create(
                    id=r["id"], name=r["name"], description=r.get("description") or "",
                    created_at=parse_dt(r.get("created_at")),
                )

            for r in rows("purchases"):
                Purchase.objects.create(
                    id=r["id"], student_id=r["student_id"], material_id=r["material_id"],
                    project_id=r.get("project_id"), quantity=dec(r["quantity"]).quantize(Decimal("0.01")),
                    unit_price=dec(r["unit_price"]).quantize(Decimal("0.0001")),
                    total_cost=money(dec(r["total_cost"])),
                    purchase_date=parse_dt(r.get("purchase_date")).date(), notes=r.get("notes") or "",
                )

            for r in rows("payments"):
                Payment.objects.create(
                    id=r["id"], student_id=r["student_id"], amount=money(dec(r["amount"])),
                    payment_method=r.get("payment_method") or Payment.Method.OTHER,
                    payment_date=parse_dt(r.get("payment_date")).date(), notes=r.get("notes") or "",
                )

            self._verify(src)
        src.close()
        self.stdout.write(self.style.SUCCESS(
            f"Imported {Student.objects.count()} students, {Material.objects.count()} materials, "
            f"{Purchase.objects.count()} purchases, {Payment.objects.count()} payments, {Project.objects.count()} projects."
        ))

    def _verify(self, src):
        """Abort the import if any student's balance differs from the old app by more than a penny."""
        old = {
            r[0]: money(dec(r[1]))
            for r in src.execute(
                "SELECT s.id, COALESCE((SELECT SUM(amount) FROM payments WHERE student_id=s.id),0)"
                " - COALESCE((SELECT SUM(total_cost) FROM purchases WHERE student_id=s.id),0) FROM students s"
            )
        }
        for student in Student.objects.with_balances():
            if abs(student.balance - old[student.id]) > Decimal("0.01"):
                raise CommandError(f"Balance mismatch for {student}: old {old[student.id]} new {student.balance}")
        self.stdout.write(f"Verified balances for {len(old)} students.")
