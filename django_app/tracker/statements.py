"""Balance summaries for students: what they owe and which purchases that covers (student prices only)."""
from dataclasses import dataclass, field
from decimal import Decimal
from urllib.parse import quote

from django.conf import settings

from .models import ZERO, Student


@dataclass
class Statement:
    student: Student
    owed: Decimal = ZERO
    credit: Decimal = ZERO
    items: list = field(default_factory=list)  # [{"name", "quantity", "unit"}] for purchases not yet paid for

    @property
    def first_name(self) -> str:
        return self.student.name.split()[0] if self.student.name.strip() else ""

    def email_subject(self) -> str:
        return f"Your materials balance with {settings.STUDIO_NAME}"

    def email_body(self) -> str:
        lines = [
            f"Hi {self.first_name},",
            "",
            f"Just a quick note that your balance for materials is £{self.owed:,.2f}.",
        ]
        if self.items:
            lines += ["", "This covers:"]
            lines += [f"- {describe(item)}" for item in self.items]
        lines += [
            "",
            "You can pay by cash or card at your next class.",
            "",
            "Thank you,",
            settings.STUDIO_SIGNOFF,
            settings.STUDIO_NAME,
        ]
        return "\r\n".join(lines)

    def mailto(self) -> str:
        if not self.student.email:
            return ""
        return (
            f"mailto:{quote(self.student.email, safe='@')}"
            f"?subject={quote(self.email_subject(), safe='')}&body={quote(self.email_body(), safe='')}"
        )


def describe(item) -> str:
    """"Jump rings × 12" or "Silver sheet, 2.5g" – quantities only, never prices."""
    qty = f"{item['quantity'].normalize():f}"
    suffix = {"gram": "g", "cm": "cm", "mm": "mm"}.get(item["unit"])
    return f"{item['name']}, {qty}{suffix}" if suffix else f"{item['name']} × {qty}"


def statement_for(student) -> Statement:
    purchases = list(student.purchases.select_related("material").order_by("purchase_date", "id"))
    paid = sum((p.amount for p in student.payments.all()), ZERO)
    charged = sum((p.total_cost for p in purchases), ZERO)
    statement = Statement(student=student)
    if paid >= charged:
        statement.credit = paid - charged
        return statement

    statement.owed = charged - paid
    # Payments clear the oldest purchases first; whatever is left (even partly) is still owed.
    remaining = paid
    grouped = {}
    for purchase in purchases:
        if remaining >= purchase.total_cost:
            remaining -= purchase.total_cost
            continue
        remaining = ZERO
        key = purchase.material_id
        if key not in grouped:
            grouped[key] = {"name": purchase.material.name, "quantity": ZERO, "unit": purchase.material.unit_type}
        grouped[key]["quantity"] += purchase.quantity
    statement.items = [dict(item, label=describe(item)) for item in grouped.values()]
    return statement
