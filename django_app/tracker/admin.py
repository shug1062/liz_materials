from django.contrib import admin
from django.db.models.deletion import ProtectedError

from .models import Category, ClassOrder, Material, Payment, Project, Purchase, Student


class PurchaseInline(admin.TabularInline):
    model = Purchase
    extra = 0
    fields = ("purchase_date", "material", "quantity", "unit_price", "total_cost", "project", "notes")
    readonly_fields = ("unit_price", "total_cost")
    autocomplete_fields = ("material",)
    show_change_link = True


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    fields = ("payment_date", "amount", "payment_method", "notes")


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "class_name", "is_sales_channel", "email", "phone")
    list_filter = ("is_sales_channel", "class_name")
    search_fields = ("name", "email", "phone", "class_name")
    inlines = [PurchaseInline, PaymentInline]

    def save_formset(self, request, form, formset, change):
        if formset.model is Purchase:
            for inline_form in formset.forms:
                if inline_form.has_changed() and inline_form.cleaned_data and not inline_form.cleaned_data.get("DELETE"):
                    obj = inline_form.instance
                    obj.set_price(reprice=obj.pk is None or "material" in inline_form.changed_data)
        super().save_formset(request, form, formset, change)


@admin.register(ClassOrder)
class ClassOrderAdmin(admin.ModelAdmin):
    list_display = ("class_name", "sort_order")
    list_editable = ("sort_order",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order")
    list_editable = ("sort_order",)
    search_fields = ("name",)


@admin.register(Material)
class MaterialAdmin(admin.ModelAdmin):
    list_display = (
        "name", "category", "pricing_type", "base_price", "pack_quantity",
        "markup_percentage", "final_price", "is_active", "sort_order",
    )
    list_editable = ("is_active", "sort_order")
    list_filter = ("is_active", "category", "pricing_type", "supplier")
    search_fields = ("name", "supplier", "notes")
    list_select_related = ("category",)

    @admin.display(description="Final price / unit")
    def final_price(self, obj):
        return f"£{obj.final_price}"

    def delete_queryset(self, request, queryset):
        try:
            super().delete_queryset(request, queryset)
        except ProtectedError:
            self.message_user(request, "Materials with purchases can't be deleted – mark them inactive instead.", level="error")


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name", "description")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("purchase_date", "student", "material", "quantity", "unit_price", "total_cost", "project")
    list_filter = ("purchase_date", "student__class_name", "material__category")
    search_fields = ("student__name", "material__name", "notes")
    autocomplete_fields = ("student", "material")
    readonly_fields = ("unit_price", "total_cost")
    date_hierarchy = "purchase_date"
    list_select_related = ("student", "material", "project")

    def save_model(self, request, obj, form, change):
        obj.set_price(reprice=not change or "material" in form.changed_data)
        super().save_model(request, obj, form, change)


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("payment_date", "student", "amount", "payment_method")
    list_filter = ("payment_method", "payment_date", "student__is_sales_channel", "student__class_name")
    search_fields = ("student__name", "notes")
    autocomplete_fields = ("student",)
    date_hierarchy = "payment_date"
    list_select_related = ("student",)
