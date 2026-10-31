from django import forms

from .models import Category, Material, Payment, Project, Purchase, Student


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, attrs=None, format="%Y-%m-%d"):
        # HTML date pickers only accept ISO dates, not the en-GB display format.
        super().__init__(attrs, format)


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
            "quantity": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}),
        }

    def __init__(self, *args, students=None, **kwargs):
        super().__init__(*args, **kwargs)
        if students is not None:
            self.fields["student"].queryset = students
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
            "amount": forms.NumberInput(attrs={"step": "0.01", "min": "0.01", "inputmode": "decimal"}),
        }

    def __init__(self, *args, students=None, **kwargs):
        super().__init__(*args, **kwargs)
        if students is not None:
            self.fields["student"].queryset = students

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


class MaterialForm(forms.ModelForm):
    category_name = forms.CharField(
        label="Category", required=False, max_length=100,
        widget=forms.TextInput(attrs={"list": "category-names", "autocomplete": "off"}),
    )

    class Meta:
        model = Material
        fields = [
            "name", "category_name", "pricing_type", "unit_type", "base_price", "pack_quantity",
            "weight_per_unit", "markup_percentage", "supplier", "supplier_url", "is_active", "is_favourite", "notes",
        ]
        labels = {"base_price": "Supplier price (£)", "pack_quantity": "Items in pack"}
        widgets = {
            "base_price": forms.NumberInput(attrs={"step": "0.0001", "min": "0", "inputmode": "decimal"}),
            "pack_quantity": forms.NumberInput(attrs={"step": "1", "min": "1", "inputmode": "decimal"}),
            "weight_per_unit": forms.NumberInput(attrs={"step": "0.0001", "min": "0", "inputmode": "decimal"}),
            "markup_percentage": forms.NumberInput(attrs={"step": "0.5", "min": "0", "inputmode": "decimal"}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.category_id:
            self.initial.setdefault("category_name", self.instance.category.name)

    def clean(self):
        data = super().clean()
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
