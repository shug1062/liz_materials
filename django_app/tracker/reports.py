"""Private money reports: monthly income by payment method, materials profit, and CSV exports for tax records."""
import csv
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse

from .models import ZERO, Material, Payment, Purchase, Sale, Student, StudioClass, money


def tax_year(day: date) -> tuple[date, date]:
    """UK tax year containing `day` (6 April to 5 April)."""
    start_year = day.year if day >= date(day.year, 4, 6) else day.year - 1
    return date(start_year, 4, 6), date(start_year + 1, 4, 5)


def tax_year_label(day: date) -> str:
    start, end = tax_year(day)
    return f"{start.year}/{str(end.year)[2:]}"


def presets(today: date) -> list[tuple[str, date | None, date | None]]:
    this_start, this_end = tax_year(today)
    last_start, last_end = tax_year(date(this_start.year - 1, 6, 1))
    return [
        (f"Tax year {this_start.year}/{str(this_end.year)[2:]}", this_start, this_end),
        (f"Tax year {last_start.year}/{str(last_end.year)[2:]}", last_start, last_end),
        (f"{today.year}", date(today.year, 1, 1), date(today.year, 12, 31)),
        ("All time", None, None),
    ]


def filtered(start, end):
    payments, purchases = Payment.objects.select_related("student"), Purchase.objects.select_related("student", "material__category")
    if start:
        payments, purchases = payments.filter(payment_date__gte=start), purchases.filter(purchase_date__gte=start)
    if end:
        payments, purchases = payments.filter(payment_date__lte=end), purchases.filter(purchase_date__lte=end)
    return payments, purchases


def filtered_sales(start, end):
    sales = Sale.objects.select_related("student")
    if start:
        sales = sales.filter(sale_date__gte=start)
    if end:
        sales = sales.filter(sale_date__lte=end)
    return sales


def monthly(payments, purchases, sales=None) -> list[dict]:
    months = {}
    money_keys = ("cash", "card", "other", "income", "sales", "cost", "lessons", "orders", "other_sales")

    def row(month):
        return months.setdefault(month, {"month": month, **{key: ZERO for key in money_keys}})

    def receive(target, method, amount):
        key = {Payment.Method.CASH: "cash", Payment.Method.CARD: "card"}.get(method, "other")
        target[key] += amount
        target["income"] += amount

    for r in payments.annotate(month=TruncMonth("payment_date")).values("month", "payment_method").annotate(total=Sum("amount")):
        receive(row(r["month"]), r["payment_method"], r["total"])
    if sales is not None:
        for r in (sales.annotate(month=TruncMonth("sale_date")).values("month", "payment_method")
                  .annotate(total=Sum("amount")).order_by()):
            target = row(r["month"])
            receive(target, r["payment_method"], r["total"])
            target["other_sales"] += r["total"]
    for r in purchases.annotate(month=TruncMonth("purchase_date")).values("month", "material__kind").annotate(
            sales=Sum("total_cost"), cost=Sum("cost_total")):
        target = row(r["month"])
        if r["material__kind"] == Material.Kind.LESSON:
            target["lessons"] += r["sales"] or ZERO
        elif r["material__kind"] == Material.Kind.ORDER:
            target["orders"] += r["sales"] or ZERO
        else:
            target["sales"] += r["sales"] or ZERO
            target["cost"] += r["cost"] or ZERO
    rows = sorted(months.values(), key=lambda m: m["month"], reverse=True)
    for m in rows:
        for key in money_keys:
            m[key] = money(m[key])
        m["profit"] = m["sales"] - m["cost"]
    return rows


def silver_grams(material, quantity):
    """Grams of silver in a sale, or None when the material has no weight to go on (e.g. packs of jump rings)."""
    if material.pricing_type == Material.PricingType.PER_GRAM:
        return quantity
    if material.weight_per_unit:
        # Per gram × item weight is always sold by the item, whatever its unit label says.
        return quantity * material.weight_per_unit
    if material.pricing_type == Material.PricingType.FIXED and material.unit_type == "gram":
        return quantity
    return None


def silver_by_class(purchases, no_class_label) -> list[dict]:
    """Silver used by each class over its whole life (or the part of it inside the chosen period)."""
    classes = {c.name: c for c in StudioClass.objects.all()}
    rows = {}
    for p in purchases.filter(material__in_silver_report=True).select_related("student", "material"):
        label = "Sales channels" if p.student.is_sales_channel else (p.class_name or no_class_label)
        row = rows.setdefault(label, {"label": label, "grams": ZERO, "sold": ZERO, "days": set(), "pieces": {}})
        grams = silver_grams(p.material, p.quantity)
        if grams is None:
            row["pieces"][p.material.name] = row["pieces"].get(p.material.name, ZERO) + p.quantity
        else:
            row["grams"] += grams
        row["sold"] += p.total_cost
        row["days"].add(p.purchase_date)
    order = {name: i for i, name in enumerate(StudioClass.ordered_class_names())}
    result = []
    for row in sorted(rows.values(), key=lambda r: (order.get(r["label"], len(order)), r["label"].lower())):
        studio_class = classes.get(row["label"])
        days = row.pop("days")
        row.update(
            start=studio_class.start_date if studio_class and studio_class.start_date else min(days),
            end=studio_class.end_date if studio_class and studio_class.end_date else max(days),
            dates_set=bool(studio_class and (studio_class.start_date or studio_class.end_date)),
            n_days=len(days),
            grams=row["grams"].quantize(Decimal("0.01")),
            pieces=sorted(row["pieces"].items()),
            n_pieces=sum(row["pieces"].values(), ZERO),
        )
        result.append(row)
    return result


def class_day(class_name: str, day: date) -> dict:
    """Everything that happened in one class session: who bought what, silver used, money taken, what's owed."""
    purchases = list(Purchase.objects.filter(class_name=class_name, purchase_date=day)
                     .select_related("student", "material").order_by("student__name", "id"))
    buyer_ids = {p.student_id for p in purchases}
    payments = list(Payment.objects.filter(payment_date=day)
                    .filter(Q(student_id__in=buyer_ids) | Q(student__class_name=class_name))
                    .select_related("student"))
    student_ids = buyer_ids | {p.student_id for p in payments}
    students = {s.pk: s for s in Student.objects.with_balances().filter(pk__in=student_ids)}

    rows = {pk: {"student": s, "items": [], "charged": ZERO, "paid": ZERO} for pk, s in students.items()}
    silver, pieces = {}, {}
    for p in purchases:
        rows[p.student_id]["items"].append(p)
        rows[p.student_id]["charged"] += p.total_cost
        if p.material.in_silver_report:
            grams = silver_grams(p.material, p.quantity)
            if grams is None:
                pieces[p.material.name] = pieces.get(p.material.name, ZERO) + p.quantity
            else:
                silver[p.material.name] = silver.get(p.material.name, ZERO) + grams
    taken = {"cash": ZERO, "card": ZERO, "other": ZERO, "total": ZERO}
    for p in payments:
        rows[p.student_id]["paid"] += p.amount
        taken[{Payment.Method.CASH: "cash", Payment.Method.CARD: "card"}.get(p.payment_method, "other")] += p.amount
        taken["total"] += p.amount
    rows = sorted(rows.values(), key=lambda r: r["student"].name.lower())
    return {
        "rows": rows,
        "charged": sum((r["charged"] for r in rows), ZERO),
        "taken": taken,
        "owed": sum((-r["student"].balance for r in rows if r["student"].balance < 0), ZERO),
        "silver": sorted((name, grams.quantize(Decimal("0.01"))) for name, grams in silver.items()),
        "silver_grams": sum(silver.values(), ZERO).quantize(Decimal("0.01")),
        "pieces": sorted(pieces.items()),
        "n_items": len(purchases),
    }


# ---------- CSV ----------

def _safe(value):
    """Stop spreadsheet apps treating text like "=SUM(...)" as a formula."""
    text = "" if value is None else str(value)
    return f"'{text}" if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def csv_response(filename: str, header: list[str], rows) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")  # BOM so Excel shows £ and accents correctly
    writer = csv.writer(response)
    writer.writerow(header)
    for r in rows:
        writer.writerow([_safe(v) if isinstance(v, str) else ("" if v is None else v) for v in r])
    return response


def monthly_csv_rows(rows):
    for m in rows:
        yield [m["month"].strftime("%Y-%m"), m["cash"], m["card"], m["other"], m["income"], m["sales"], m["cost"],
               m["profit"], m["lessons"], m["orders"], m["other_sales"]]


MONTHLY_HEADER = ["Month", "Cash received", "Card received", "Other received", "Total received",
                  "Materials sold", "Materials cost", "Materials profit", "Lesson fees", "Orders at cost",
                  "Other sales (jewellery, courses etc.)"]

PAYMENTS_HEADER = ["Date", "Name", "Type", "Class / where", "Method", "Amount", "Notes"]


def payments_csv_rows(payments, sales=None):
    """Every payment, plus (when given) every one-off sale – together that's all money received."""
    rows = [(p.payment_date, 0, p.id, [p.payment_date.isoformat(), p.student.name,
                                       "Sales channel" if p.student.is_sales_channel else "Student",
                                       p.student.class_name, p.payment_method, p.amount, p.notes])
            for p in payments]
    for s in sales if sales is not None else ():
        rows.append((s.sale_date, 1, s.id, [s.sale_date.isoformat(), s.student.name if s.student else "",
                                            f"Sale – {s.get_sale_type_display()}", s.where, s.payment_method,
                                            s.amount, s.description]))
    for *_, row in sorted(rows, key=lambda r: r[:3]):
        yield row


SALES_HEADER = ["Date", "Student", "Class", "Type", "Material", "Category", "Quantity", "Unit", "Price each",
                "Total charged", "Cost each", "Total cost", "Profit", "Cost estimated", "Silver £/kg used for cost"]


def sales_csv_rows(purchases):
    for p in purchases.order_by("purchase_date", "id"):
        cost = p.cost_total if p.cost_total is not None else ZERO
        yield [p.purchase_date.isoformat(), p.student.name, p.class_name, p.material.get_kind_display(), p.material.name,
               p.material.category.name if p.material.category else "", p.quantity, p.material.unit_type,
               p.unit_price, p.total_cost, p.unit_cost, p.cost_total, p.total_cost - cost,
               "Yes" if p.cost_is_estimate else "No", p.silver_rate]
