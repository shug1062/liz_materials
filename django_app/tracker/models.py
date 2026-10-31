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

    def active(self):
        return self.filter(is_archived=False)


class Student(models.Model):
    name = models.CharField(max_length=200)
    class_name = models.CharField("class", max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)
    is_sales_channel = models.BooleanField(
        "sales channel", default=False, help_text="A shop/market rather than a class student."
    )
    is_archived = models.BooleanField("archived", default=False, help_text="Hidden from everyday lists; history is kept.")
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    objects = StudentQuerySet.as_manager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.class_name:
            # Reuse an existing class's spelling so "previous student" doesn't become a second class.
            existing = StudioClass.objects.filter(name__iexact=self.class_name.strip()).values_list("name", flat=True).first()
            self.class_name = existing or self.class_name.strip()
        super().save(*args, **kwargs)
        if self.class_name and not self.is_sales_channel and not StudioClass.objects.filter(name=self.class_name).exists():
            StudioClass.objects.create(name=self.class_name, sort_order=StudioClass.objects.count())

    def get_absolute_url(self):
        return reverse("tracker:student_detail", args=[self.pk])

    @property
    def balance(self) -> Decimal:
        """Positive = credit, negative = owes. Needs with_balances()."""
        return self.total_payments - self.total_purchases


class StudioClass(models.Model):
    """A class/course. Students join one by having its name as their class_name."""

    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True, help_text="After this date the class counts as finished.")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "class"
        verbose_name_plural = "classes"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("tracker:class_detail", args=[self.pk])

    @property
    def status(self) -> str:
        today = timezone.localdate()
        if self.end_date and self.end_date < today:
            return "finished"
        if self.start_date and self.start_date > today:
            return "upcoming"
        return "current"

    @classmethod
    def ordered_class_names(cls, include_finished=True) -> list[str]:
        classes = cls.objects.all()
        if not include_finished:
            classes = [c for c in classes if c.status != "finished"]
        return [c.name for c in classes]


class StudioSettings(models.Model):
    backup_directory = models.CharField(max_length=1000, blank=True, null=True)
    last_backup_date = models.DateField(null=True, blank=True)

    class Meta:
        verbose_name = "studio settings"
        verbose_name_plural = "studio settings"


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Material(models.Model):
    class Kind(models.TextChoices):
        MATERIAL = "material", "Material"
        LESSON = "lesson", "Lesson fee"
        ORDER = "order", "Order at cost (type the amount)"

    class PricingType(models.TextChoices):
        FIXED = "fixed", "Fixed price (pack / item)"
        PER_GRAM = "per_gram", "Per gram (bulk)"
        PER_GRAM_ITEM = "per_gram_item", "Per gram × item weight"

    UNIT_CHOICES = [(u, u) for u in ("item", "gram", "piece", "sheet", "cm", "mm")]

    name = models.CharField(max_length=200)
    kind = models.CharField("type", max_length=20, choices=Kind.choices, default=Kind.MATERIAL,
                            help_text="Lesson fees and orders at cost are kept out of materials profit.")
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
    markup_ok = models.BooleanField("low markup is deliberate", default=False,
                                    help_text="Don't warn about a thin margin unless silver prices mean selling at a loss.")
    supplier = models.CharField(max_length=100, blank=True, default="Cooksongold")
    supplier_url = models.URLField(max_length=500, blank=True)
    is_active = models.BooleanField("active", default=True, help_text="Inactive materials are hidden from new purchases.")
    is_favourite = models.BooleanField("quick button", default=False, help_text="Show as a quick button in class mode.")
    is_silver = models.BooleanField("silver", default=False, help_text="Cost follows the silver price on the day of each sale.")
    in_silver_report = models.BooleanField("count in silver report", default=False,
                                           help_text="Include in the silver used by class report on the Reports page.")
    price_date = models.DateField("price date", default=timezone.localdate,
                                  help_text="When the supplier price was last checked.")
    sort_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category__sort_order", "category__name", "sort_order", "name"]

    def __str__(self):
        return self.name

    @property
    def is_counted(self) -> bool:
        """Sold in whole units (items) rather than measured amounts (grams, cm)."""
        return self.unit_type in {"item", "piece", "sheet"}

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

    @classmethod
    def course_fee(cls) -> "Material":
        """Hidden lesson item that term and course fees are charged against (the amount is set per charge)."""
        fee, _ = cls.objects.get_or_create(
            name="Course fee", kind=cls.Kind.LESSON,
            defaults={"base_price": ZERO, "unit_type": "item", "supplier": "", "is_active": False},
        )
        return fee


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
    # Studio's own cost, frozen at the time of sale so later supplier price changes don't rewrite history.
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    cost_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    cost_is_estimate = models.BooleanField(default=False, help_text="Worked out from price ÷ markup (recorded before costs were saved).")
    silver_rate = models.DecimalField("silver £/kg", max_digits=10, decimal_places=2, null=True, blank=True,
                                      help_text="Silver price on the day of sale, used for the cost of silver materials.")
    # The student's class when they bought it, so moving class next term doesn't move past sales.
    class_name = models.CharField("class", max_length=100, blank=True)
    purchase_date = models.DateField(default=timezone.localdate)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-purchase_date", "-id"]

    def __str__(self):
        return f"{self.student} – {self.material} × {self.quantity}"

    def save(self, *args, **kwargs):
        if self._state.adding and not self.class_name:
            self.class_name = self.student.class_name
        if self.material.is_silver and self.quantity is not None:
            from . import silver
            silver.apply(self)
        super().save(*args, **kwargs)

    def set_price(self, reprice: bool):
        """Lock in the material's current price and cost, or keep the originals when editing."""
        if reprice or self.unit_price is None:
            self.unit_price = self.material.final_price
            self.unit_cost = self.material.cost_per_item.quantize(UNIT_PRICE_PLACES, rounding=ROUND_HALF_UP)
            self.cost_is_estimate = False
        self.total_cost = money(self.quantity * self.unit_price)
        self.cost_total = money(self.quantity * self.unit_cost) if self.unit_cost is not None else None


def estimated_unit_cost(unit_price: Decimal, markup_percentage: Decimal) -> Decimal:
    """Best guess at an old purchase's cost: take the material's markup back off the price charged."""
    return (unit_price / (1 + markup_percentage / 100)).quantize(UNIT_PRICE_PLACES, rounding=ROUND_HALF_UP)


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


class Sale(models.Model):
    """Something sold and paid for on the spot – jewellery, a course, materials at a market – outside a student's tab."""

    class Type(models.TextChoices):
        JEWELLERY = "jewellery", "Jewellery"
        COURSE = "course", "Course / workshop"
        MATERIALS = "materials", "Materials"
        VOUCHER = "voucher", "Gift voucher"
        OTHER = "other", "Other"

    sale_date = models.DateField("date", default=timezone.localdate)
    sale_type = models.CharField("what was sold", max_length=20, choices=Type.choices, default=Type.JEWELLERY)
    description = models.CharField(max_length=200, blank=True, help_text="e.g. “Silver hoop earrings”")
    amount = models.DecimalField("amount (£)", max_digits=10, decimal_places=2)
    payment_method = models.CharField("paid by", max_length=20, choices=Payment.Method.choices, default=Payment.Method.CASH)
    student = models.ForeignKey(Student, null=True, blank=True, on_delete=models.SET_NULL, related_name="sales",
                                help_text="Optional – leave blank for someone who isn't a student.")
    where = models.CharField(max_length=100, blank=True, help_text="A class, or e.g. “Christmas market”.")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-sale_date", "-id"]

    def __str__(self):
        return f"{self.get_sale_type_display()} – £{self.amount}"


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
    source = models.CharField(max_length=20, default="cooksongold")

    class Meta:
        ordering = ["-fetched_at"]
        get_latest_by = "fetched_at"

    def __str__(self):
        return f"£{self.price_per_kg}/kg on {self.fetched_at:%d %b %Y}"

    @property
    def price_per_gram(self) -> Decimal:
        return self.price_per_kg / 1000
