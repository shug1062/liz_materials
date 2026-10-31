import sqlite3
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tracker.models import (
    PENNY, Category, Material, Payment, Project, Purchase, Student, StudioClass, estimated_unit_cost, money,
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


def penny_totals(purchases) -> dict[int, Decimal]:
    """Round purchases to the penny so each student's still add up to the old app's (rounded) total.

    Rounding each unrounded legacy total on its own drifts a few pence per student; the spare pennies
    go to the purchases with the largest remainders instead.
    """
    by_student = {}
    for r in purchases:
        by_student.setdefault(r["student_id"], []).append((r["id"], dec(r["total_cost"])))
    result = {}
    for items in by_student.values():
        floors = {pid: exact.quantize(PENNY, rounding=ROUND_FLOOR) for pid, exact in items}
        spare = int((money(sum(exact for _, exact in items)) - sum(floors.values())) / PENNY)
        by_remainder = sorted(items, key=lambda item: item[1] - floors[item[0]], reverse=True)
        for i, (pid, _) in enumerate(by_remainder):
            result[pid] = floors[pid] + (PENNY if i < spare else 0)
    return result


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
        parser.add_argument("--recover-from", type=Path, action="append", default=[],
                            help="Older copy of the old database to recover deleted materials' names from.")

    def handle(self, legacy_db: Path, if_empty=False, recover_from=(), **options):
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
                    StudioClass.objects.update_or_create(name=r["class_name"], defaults={"sort_order": r["sort_order"]})

            category_order = {}
            if "category_order" in tables:
                category_order = {r["category_name"]: r["sort_order"] for r in rows("category_order")}
            material_order = {}
            if "material_order" in tables:
                material_order = {r["material_id"]: r["sort_order"] for r in rows("material_order")}

            categories = {}

            def create_material(r, **overrides):
                cat_name = (r.get("category") or "").strip()
                category = None
                if cat_name:
                    key = cat_name.lower()
                    if key not in categories:
                        categories[key] = Category.objects.create(
                            name=cat_name, sort_order=category_order.get(cat_name, 1000)
                        )
                    category = categories[key]
                fields = dict(
                    id=r["id"], name=r["name"], category=category, unit_type=r.get("unit_type") or "item",
                    pricing_type=PRICING_TYPES.get(r.get("pricing_type") or "fixed", "fixed"),
                    base_price=dec(r["base_price"]).quantize(Decimal("0.0001")),
                    pack_quantity=dec(r.get("pack_quantity"), "1") or Decimal("1"),
                    weight_per_unit=dec(r["weight_per_unit"]).quantize(Decimal("0.0001")) if r.get("weight_per_unit") else None,
                    markup_percentage=dec(r.get("markup_percentage")).quantize(Decimal("0.01")),
                    supplier=r.get("supplier") or "",
                    supplier_url=RENAMED_LINKS.get(r.get("supplier_url") or "", r.get("supplier_url") or ""),
                    is_active=bool(r.get("is_active", 1)), sort_order=material_order.get(r["id"], 1000),
                    is_silver=any(w in r["name"].lower() for w in ("silver", "sterling")),
                    price_date=timezone.localtime(parse_dt(r.get("last_updated"))).date(),
                    notes=r.get("notes") or "",
                )
                fields.update(overrides)
                return Material.objects.create(**fields)

            for r in rows("materials"):
                create_material(r)
            self._recreate_deleted_materials(src, recover_from, create_material)

            for r in rows("projects"):
                Project.objects.create(
                    id=r["id"], name=r["name"], description=r.get("description") or "",
                    created_at=parse_dt(r.get("created_at")),
                )

            markups = dict(Material.objects.values_list("id", "markup_percentage"))
            purchase_rows = rows("purchases")
            totals = penny_totals(purchase_rows)
            for r in purchase_rows:
                quantity = dec(r["quantity"]).quantize(Decimal("0.01"))
                unit_price = dec(r["unit_price"]).quantize(Decimal("0.0001"))
                unit_cost = estimated_unit_cost(unit_price, markups[r["material_id"]])
                Purchase.objects.create(
                    id=r["id"], student_id=r["student_id"], material_id=r["material_id"],
                    project_id=r.get("project_id"), quantity=quantity, unit_price=unit_price,
                    total_cost=totals[r["id"]],
                    unit_cost=unit_cost, cost_total=money(quantity * unit_cost), cost_is_estimate=True,
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

    def _recreate_deleted_materials(self, src, recover_from, create_material):
        """The old app let materials be deleted while purchases still pointed at them; keep those sales."""
        missing = src.execute(
            "SELECT material_id, MAX(quantity <> CAST(quantity AS INTEGER)), MAX(purchase_date) FROM purchases"
            " WHERE material_id NOT IN (SELECT id FROM materials) GROUP BY material_id"
        ).fetchall()
        if not missing:
            return
        known = {}
        for path in recover_from:
            old = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            old.row_factory = sqlite3.Row
            for r in old.execute("SELECT * FROM materials"):
                known.setdefault(r["id"], dict(r))
            old.close()
        note = "Deleted in the old app; brought back so past purchases keep their history."
        for material_id, fractional, last_sold in missing:
            latest = src.execute("SELECT unit_price FROM purchases WHERE material_id=? ORDER BY purchase_date DESC, id DESC",
                                 (material_id,)).fetchone()[0]
            if material_id in known:
                material = create_material(known[material_id], is_active=False, notes=note)
            else:
                # Name unknown: price it at what students last paid, with no markup, so profit isn't overstated.
                material = create_material(
                    {"id": material_id, "name": f"Deleted material #{material_id}", "category": "Deleted materials",
                     "unit_type": "gram" if fractional else "item", "pricing_type": "per_kg" if fractional else "fixed",
                     "base_price": latest, "last_updated": last_sold, "supplier": ""},
                    is_active=False, notes=note + " Its name wasn't in any older copy – rename it if you know it.",
                )
            self.stdout.write(self.style.WARNING(f"Recreated deleted material #{material_id}: {material.name}"))

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
