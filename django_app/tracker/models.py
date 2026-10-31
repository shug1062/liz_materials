from decimal import ROUND_HALF_UP, Decimal

from django.db import models
from django.db.models import DecimalField, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.utils import timezone

PENNY = Decimal("0.01")
UNIT_PRICE_PLACES = Decimal("0.0001")
ZERO = Decimal("0")


def money(value: Decimal) -> Decimal:
    return value.quantize(PENNY, rounding=ROUND_HALF_UP)


class StudentQuerySet(models.QuerySet):
    def with_balances(self):
        money_field = DecimalField(max_digits=12, decimal_places=2)

        def total(model, field):
            # Subqueries avoid the row multiplication a double JOIN would cause.
            sums = (
                model.objects.filter(student=OuterRef("pk"))
                .order_by()
                .values("student")
                .annotate(total=Sum(field))
                .values("total")
            )
            return Coalesce(Subquery(sums, output_field=money_field), Value(ZERO), output_field=money_field)

        return self.annotate(
            total_purchases=total(Purchase, "total_cost"),
            total_payments=total(Payment, "amount"),
        )


class Student(models.Model):
    name = models.CharField(max_length=200)
    class_name = models.CharField("class", max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    is_sales_channel = models.BooleanField(
        "sales channel", default=False, help_text="A shop/market rather than a class student."
    )
    created_at = models.DateTimeField(default=timezone.now)

    objects = StudentQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("tracker:student_detail", args=[self.pk])

    @property
    def balance(self) -> Decimal:
        """Positive = credit, negative = owes. Needs with_balances()."""
        return self.total_payments - self.total_purchases


class ClassOrder(models.Model):
    class_name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "class_name"]

    def __str__(self):
        return self.class_name

    @classmethod
    def ordered_class_names(cls) -> list[str]:
        used = set(
            Student.objects.exclude(class_name="").values_list("class_name", flat=True).distinct()
        )
        ordered = [c for c in cls.objects.values_list("class_name", flat=True) if c in used]
        return ordered + sorted(used - set(ordered))


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Material(models.Model):
    class PricingType(models.TextChoices):
        FIXED = "fixed", "Fixed price (pack / item)"
        PER_GRAM = "per_gram", "Per gram (bulk)"
        PER_GRAM_ITEM = "per_gram_item", "Per gram × item weight"

    UNIT_CHOICES = [(u, u) for u in ("item", "gram", "piece", "sheet", "cm", "mm")]

    name = models.CharField(max_length=200)
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL)
    unit_type = models.CharField(max_length=20, choices=UNIT_CHOICES, default="item")
    pricing_type = models.CharField(max_length=20, choices=PricingType.choices, default=PricingType.FIXED)
    base_price = models.DecimalField(
        max_digits=10, decimal_places=4, help_text="Pack price, or price per gram for per-gram types."
    )
    pack_quantity = models.DecimalField(max_digits=10, decimal_places=3, default=Decimal("1"))
    weight_per_unit = models.DecimalField(
        "weight per item (g)", max_digits=10, decimal_places=4, null=True, blank=True
    )
    markup_percentage = models.DecimalField("markup %", max_digits=6, decimal_places=2, default=ZERO)
    supplier = models.CharField(max_length=100, blank=True, default="Cooksongold")
    supplier_url = models.URLField(max_length=500, blank=True)
    is_active = models.BooleanField("active", default=True, help_text="Inactive materials are hidden from new purchases.")
    sort_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category__sort_order", "category__name", "sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def cost_per_item(self) -> Decimal:
        if self.pricing_type == self.PricingType.PER_GRAM_ITEM and self.weight_per_unit:
            return self.base_price * self.weight_per_unit
        if self.pack_quantity and self.pack_quantity > 0:
            return self.base_price / self.pack_quantity
        return self.base_price

    @property
    def final_price(self) -> Decimal:
        """Price per unit charged to students, kept to 4dp for per-gram items."""
        price = self.cost_per_item * (1 + self.markup_percentage / 100)
        return price.quantize(UNIT_PRICE_PLACES, rounding=ROUND_HALF_UP)


class Project(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Purchase(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="purchases")
    # PROTECT: a material with purchase history can be deactivated but not deleted.
    material = models.ForeignKey(Material, on_delete=models.PROTECT, related_name="purchases")
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="purchases")
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=12, decimal_places=4)
    total_cost = models.DecimalField(max_digits=10, decimal_places=2)
    purchase_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-purchase_date", "-id"]

    def __str__(self):
        return f"{self.student} – {self.material} × {self.quantity}"

    def set_price(self, reprice: bool):
        """Lock in the material's current price, or keep the original price when editing."""
        if reprice or self.unit_price is None:
            self.unit_price = self.material.final_price
        self.total_cost = money(self.quantity * self.unit_price)


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "Cash"
        CARD = "Card"
        BANK_TRANSFER = "Bank Transfer"
        OTHER = "Other"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    payment_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-payment_date", "-id"]

    def __str__(self):
        return f"{self.student} – £{self.amount}"


class PriceChange(models.Model):
    material = models.ForeignKey(Material, on_delete=models.CASCADE, related_name="price_changes")
    old_price = models.DecimalField(max_digits=10, decimal_places=4)
    new_price = models.DecimalField(max_digits=10, decimal_places=4)
    old_weight = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    new_weight = models.DecimalField(max_digits=10, decimal_places=4, null=True, blank=True)
    source = models.CharField(max_length=20, default="supplier")
    changed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.material}: {self.old_price} → {self.new_price}"

    @property
    def percent_change(self):
        if not self.old_price:
            return None
        return (self.new_price - self.old_price) / self.old_price * 100


class SilverPrice(models.Model):
    price_per_kg = models.DecimalField(max_digits=10, decimal_places=2)
    fetched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-fetched_at"]
        get_latest_by = "fetched_at"

    def __str__(self):
        return f"£{self.price_per_kg}/kg on {self.fetched_at:%d %b %Y}"

    @property
    def price_per_gram(self) -> Decimal:
        return self.price_per_kg / 1000
