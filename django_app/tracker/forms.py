from decimal import Decimal
from pathlib import Path

from django import forms
from django.utils import timezone

from .models import Category, Material, Payment, Project, Purchase, Student, StudioClass


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None, format="%Y-%m-%d"):
        # HTML date pickers only accept ISO dates, not the en-GB display format.
        super().__init__(attrs, format)


class DecimalInput(forms.TextInput):
    """Number keypad on the iPad, but unlike type=number, scrolling over it can't change the value."""

    def __init__(self, attrs=None):
        super().__init__({"inputmode": "decimal", "autocomplete": "off", **(attrs or {})})


def student_label(student) -> str:
    """"Kate – Thurs 11am" so students who share a first name can be told apart."""
    label = f"{student.name} – {student.class_name}" if student.class_name else student.name
    return f"{label} (archived)" if student.is_archived else label


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["name", "class_name", "email", "phone", "notes", "is_sales_channel"]
        widgets = {
            "class_name": forms.TextInput(attrs={"list": "class-names"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ["student", "purchase_date", "material", "quantity", "project", "notes"]
        widgets = {
            "purchase_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "quantity": DecimalInput(),
        }

    def __init__(self, *args, students=None, **kwargs):
        super().__init__(*args, **kwargs)
        if students is not None:
            self.fields["student"].queryset = students
        self.fields["student"].label_from_instance = student_label
        materials = Material.objects.select_related("category")
        if self.instance.pk:
            # Keep an inactive material selectable when editing an old purchase.
            materials = materials.filter(is_active=True) | materials.filter(pk=self.instance.material_id)
        else:
            materials = materials.filter(is_active=True)
        self.fields["material"].queryset = materials
        self.fields["material"].label_from_instance = (
            lambda m: f"{m.name} ({m.category})" if m.category else m.name
        )
        self.fields["project"].queryset = Project.objects.all()

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]
        if quantity <= 0:
            raise forms.ValidationError("Quantity must be more than zero.")
        return quantity

    def save(self, commit=True):
        purchase = super().save(commit=False)
        purchase.set_price(reprice=purchase.pk is None or "material" in self.changed_data)
        if commit:
            purchase.save()
        return purchase


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["student", "payment_date", "amount", "payment_method", "notes"]
        widgets = {
            "payment_date": DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
            "amount": DecimalInput(),
        }

    def __init__(self, *args, students=None, **kwargs):
        super().__init__(*args, **kwargs)
        if students is not None:
            self.fields["student"].queryset = students
        self.fields["student"].label_from_instance = student_label

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Amount must be more than zero.")
        return amount


class PaymentFilterForm(forms.Form):
    GROUP_CHOICES = [("", "Everyone"), ("class", "Class students"), ("sales", "Sales channels")]

    group = forms.ChoiceField(choices=GROUP_CHOICES, required=False)
    student = forms.ModelChoiceField(queryset=Student.objects.all(), required=False, empty_label="All")
    start = forms.DateField(required=False, widget=DateInput(), label="From")
    end = forms.DateField(required=False, widget=DateInput(), label="To")


class DateRangeForm(forms.Form):
    start = forms.DateField(required=False, widget=DateInput(), label="From")
    end = forms.DateField(required=False, widget=DateInput(), label="To")


class CourseFeeForm(forms.Form):
    description = forms.CharField(label="What it's for", max_length=200,
                                  widget=forms.TextInput(attrs={"placeholder": "e.g. Autumn term – 10 weeks"}))
    amount = forms.DecimalField(label="Fee per student (£)", max_digits=10, decimal_places=2,
                                min_value=Decimal("0.01"), widget=DecimalInput())
    charge_date = forms.DateField(label="Date", widget=DateInput(), initial=timezone.localdate)


class TermDatesForm(forms.Form):
    start = forms.DateField(required=False, widget=DateInput(), label="Start date")
    end = forms.DateField(required=False, widget=DateInput(), label="End date")

    def clean(self):
        data = super().clean()
        if not data.get("start") and not data.get("end") and not self.errors:
            raise forms.ValidationError("Enter a start date, an end date, or both.")
        if data.get("start") and data.get("end") and data["end"] < data["start"]:
            self.add_error("end", "The end date is before the start date.")
        return data


class SilverPriceForm(forms.Form):
    day = forms.DateField(widget=DateInput(), label="Date")
    price_per_kg = forms.DecimalField(
        label="£ per kg (inc VAT)", max_digits=10, decimal_places=2, min_value=Decimal("0.01"),
        widget=DecimalInput(),
    )

    def clean_day(self):
        day = self.cleaned_data["day"]
        if day > timezone.localdate():
            raise forms.ValidationError("The date can't be in the future.")
        return day


class BackupSettingsForm(forms.Form):
    backup_directory = forms.CharField(
        label="OneDrive backup folder",
        required=False,
        max_length=1000,
        widget=forms.TextInput(attrs={"autocomplete": "off", "placeholder": "/Users/you/OneDrive/Studio Backups"}),
        help_text="Enter the full folder path inside your synced OneDrive folder. Leave blank to turn off the OneDrive copy.",
    )

    def clean_backup_directory(self):
        directory = self.cleaned_data["backup_directory"].strip()
        if not directory:
            return ""
        path = Path(directory).expanduser()
        if not path.is_absolute():
            raise forms.ValidationError("Enter a full folder path, not a relative path.")
        return str(path)


class MaterialForm(forms.ModelForm):
    category_name = forms.CharField(
        label="Category", required=False, max_length=100,
        widget=forms.TextInput(attrs={"list": "category-names", "autocomplete": "off"}),
    )

    class Meta:
        model = Material
        fields = [
            "name", "kind", "category_name", "pricing_type", "unit_type", "base_price", "pack_quantity",
            "weight_per_unit", "markup_percentage", "markup_ok", "supplier", "supplier_url", "is_active", "is_favourite",
            "is_silver", "in_silver_report", "price_date", "notes",
        ]
        labels = {"base_price": "Supplier price (£)", "pack_quantity": "Items in pack"}
        widgets = {
            "price_date": DateInput(),
            "base_price": DecimalInput(),
            "pack_quantity": DecimalInput(),
            "weight_per_unit": DecimalInput(),
            "markup_percentage": DecimalInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["price_date"].required = False
        # A callable model default adds a hidden "initial" input, which would make the date always look changed.
        self.fields["price_date"].show_hidden_initial = False
        self.fields["kind"].required = False
        self.fields["base_price"].required = False
        if self.instance.category_id:
            self.initial.setdefault("category_name", self.instance.category.name)

    def clean_kind(self):
        return self.cleaned_data["kind"] or self.instance.kind or Material.Kind.MATERIAL

    def clean_price_date(self):
        return self.cleaned_data["price_date"] or self.instance.price_date or timezone.localdate()

    def clean(self):
        data = super().clean()
        if data.get("kind") == Material.Kind.ORDER:
            # Students are charged exactly the amount typed in: £1 × the number of pounds.
            data.update(pricing_type=Material.PricingType.FIXED, base_price=Decimal("1"), pack_quantity=Decimal("1"),
                        weight_per_unit=None, markup_percentage=Decimal("0"), is_silver=False, in_silver_report=False)
            for name in ("base_price", "pack_quantity", "weight_per_unit", "markup_percentage"):
                self.errors.pop(name, None)
            return data
        if data.get("kind") == Material.Kind.LESSON:
            data["is_silver"] = data["in_silver_report"] = False
        if data.get("base_price") is None and "base_price" not in self.errors:
            self.add_error("base_price", "Enter the supplier price.")
        if data.get("pricing_type") == Material.PricingType.PER_GRAM_ITEM and not data.get("weight_per_unit"):
            self.add_error("weight_per_unit", "Enter the weight of one item (or use “Fetch from supplier”).")
        if data.get("pack_quantity") is not None and data["pack_quantity"] <= 0:
            self.add_error("pack_quantity", "Must be at least 1.")
        return data

    def save(self, commit=True):
        name = " ".join(self.cleaned_data.get("category_name", "").split())
        category = None
        if name:
            # Reuse an existing category regardless of capitalisation, as the old app did.
            category = Category.objects.filter(name__iexact=name).first() or Category.objects.create(
                name=name, sort_order=Category.objects.count()
            )
        self.instance.category = category
        return super().save(commit)


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ["name", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class StudioClassForm(forms.ModelForm):
    class Meta:
        model = StudioClass
        fields = ["name", "start_date", "end_date", "notes"]
        widgets = {"start_date": DateInput(), "end_date": DateInput(), "notes": forms.Textarea(attrs={"rows": 2})}
        help_texts = {"end_date": "Leave blank for an ongoing class. Students in finished classes can be archived."}

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        clash = StudioClass.objects.filter(name__iexact=name).exclude(pk=self.instance.pk).first()
        if clash:
            raise forms.ValidationError(f"There's already a class called “{clash.name}”.")
        return name

    def clean(self):
        data = super().clean()
        if data.get("start_date") and data.get("end_date") and data["end_date"] < data["start_date"]:
            self.add_error("end_date", "The end date is before the start date.")
        return data
