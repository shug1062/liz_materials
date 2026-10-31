"""Private money reports: monthly income by payment method, materials profit, and CSV exports for tax records."""
import csv
from datetime import date

from django.db.models import Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse

from .models import ZERO, Material, Payment, Purchase, money


def tax_year(day: date) -> tuple[date, date]:
    """UK tax year containing `day` (6 April to 5 April)."""
    start_year = day.year if day >= date(day.year, 4, 6) else day.year - 1
    return date(start_year, 4, 6), date(start_year + 1, 4, 5)


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


def monthly(payments, purchases) -> list[dict]:
    months = {}
    money_keys = ("cash", "card", "other", "income", "sales", "cost", "lessons", "orders")

    def row(month):
        return months.setdefault(month, {"month": month, **{key: ZERO for key in money_keys}})

    for r in payments.annotate(month=TruncMonth("payment_date")).values("month", "payment_method").annotate(total=Sum("amount")):
        target = row(r["month"])
        key = {Payment.Method.CASH: "cash", Payment.Method.CARD: "card"}.get(r["payment_method"], "other")
        target[key] += r["total"]
        target["income"] += r["total"]
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
               m["profit"], m["lessons"], m["orders"]]


MONTHLY_HEADER = ["Month", "Cash received", "Card received", "Other received", "Total received",
                  "Materials sold", "Materials cost", "Materials profit", "Lesson fees", "Orders at cost"]

PAYMENTS_HEADER = ["Date", "Name", "Type", "Class", "Method", "Amount", "Notes"]


def payments_csv_rows(payments):
    for p in payments.order_by("payment_date", "id"):
        yield [p.payment_date.isoformat(), p.student.name, "Sales channel" if p.student.is_sales_channel else "Student",
               p.student.class_name, p.payment_method, p.amount, p.notes]


SALES_HEADER = ["Date", "Student", "Class", "Type", "Material", "Category", "Quantity", "Unit", "Price each",
                "Total charged", "Cost each", "Total cost", "Profit", "Cost estimated", "Silver £/kg used for cost"]


def sales_csv_rows(purchases):
    for p in purchases.order_by("purchase_date", "id"):
        cost = p.cost_total if p.cost_total is not None else ZERO
        yield [p.purchase_date.isoformat(), p.student.name, p.class_name, p.material.get_kind_display(), p.material.name,
               p.material.category.name if p.material.category else "", p.quantity, p.material.unit_type,
               p.unit_price, p.total_cost, p.unit_cost, p.cost_total, p.total_cost - cost,
               "Yes" if p.cost_is_estimate else "No", p.silver_rate]
