from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, ProtectedError, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import statements, suppliers, undo
from .forms import (
    DateRangeForm, MaterialForm, PaymentFilterForm, PaymentForm, ProjectForm, PurchaseForm, StudentForm,
)
from .models import (
    ZERO, Category, ClassOrder, Material, Payment, PriceChange, Project, Purchase, SilverPrice, Student, money,
)

NO_CLASS = "No class assigned"


def _next_url(request, default):
    url = request.POST.get("next") or request.GET.get("next")
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return url
    return default


def _method_totals(payments):
    totals = {m["payment_method"]: m["total"] for m in payments.values("payment_method").annotate(total=Sum("amount"))}
    return {
        "cash": totals.get(Payment.Method.CASH, ZERO),
        "card": totals.get(Payment.Method.CARD, ZERO),
        "total": sum(totals.values(), ZERO),
    }


def dashboard(request):
    class_students = Student.objects.with_balances().filter(is_sales_channel=False)
    balances = [s.balance for s in class_students]
    class_payments = Payment.objects.filter(student__is_sales_channel=False)
    channels = Student.objects.filter(is_sales_channel=True)
    channel_totals = [(c, _method_totals(c.payments.all())) for c in channels]

    class_counts = dict(
        Student.objects.filter(is_sales_channel=False)
        .exclude(class_name="")
        .values_list("class_name")
        .annotate(n=Count("id"))
    )
    classes = [(name, class_counts.get(name, 0)) for name in ClassOrder.ordered_class_names() if name in class_counts]

    return render(request, "tracker/dashboard.html", {
        "class_totals": _method_totals(class_payments),
        "material_count": Material.objects.filter(is_active=True).count(),
        "class_debt": -sum((b for b in balances if b < 0), ZERO),
        "class_credit": sum((b for b in balances if b > 0), ZERO),
        "channel_totals": channel_totals,
        "sales_totals": _method_totals(Payment.objects.filter(student__is_sales_channel=True)),
        "classes": classes,
        "recent_purchases": Purchase.objects.select_related("student", "material", "project")[:10],
        "recent_payments": Payment.objects.select_related("student")[:10],
    })


def student_list(request):
    selected = request.GET.get("class_name", "")
    students = Student.objects.with_balances().filter(is_sales_channel=False)
    groups = {}
    for s in students:
        groups.setdefault(s.class_name or NO_CLASS, []).append(s)
    order = ClassOrder.ordered_class_names() + [NO_CLASS]
    grouped = []
    for name in order:
        if name in groups:
            members = groups[name]
            grouped.append({
                "name": name,
                "students": members,
                "owed": -sum((s.balance for s in members if s.balance < 0), ZERO),
                "credit": sum((s.balance for s in members if s.balance > 0), ZERO),
                "open": not selected or selected == name,
            })
    return render(request, "tracker/student_list.html", {
        "groups": grouped,
        "selected": selected,
        "no_class": NO_CLASS,
        "channels": Student.objects.with_balances().filter(is_sales_channel=True),
    })


def student_detail(request, pk):
    student = get_object_or_404(Student.objects.with_balances(), pk=pk)
    return render(request, "tracker/student_detail.html", {
        "student": student,
        "purchases": student.purchases.select_related("material", "project"),
        "payments": student.payments.all(),
        "statement": statements.statement_for(student),
    })


def student_statement(request, pk):
    """Print-friendly statement: what's owed, the items it covers, and the full account history."""
    student = get_object_or_404(Student, pk=pk)
    history = sorted(
        [(p.purchase_date, p.material.name, p.quantity, p.material.unit_type, p.total_cost, None)
         for p in student.purchases.select_related("material")]
        + [(p.payment_date, f"Payment – {p.payment_method.lower()}", None, "", None, p.amount)
           for p in student.payments.all()],
        key=lambda row: row[0],
    )
    return render(request, "tracker/statement.html", {
        "student": student,
        "statement": statements.statement_for(student),
        "history": history,
        "today": timezone.localdate(),
        "studio_name": settings.STUDIO_NAME,
        "studio_signoff": settings.STUDIO_SIGNOFF,
    })


def balances_to_chase(request):
    owing = [s for s in Student.objects.with_balances().filter(is_sales_channel=False) if s.balance < 0]
    rows = sorted((statements.statement_for(s) for s in owing), key=lambda st: -st.owed)
    return render(request, "tracker/balances.html", {"rows": rows, "total": sum((r.owed for r in rows), ZERO)})


def student_form(request, pk=None):
    student = get_object_or_404(Student, pk=pk) if pk else None
    form = StudentForm(request.POST or None, instance=student, initial={"class_name": request.GET.get("class_name", "")})
    if request.method == "POST" and form.is_valid():
        student = form.save()
        messages.success(request, f"Saved {student.name}.")
        return redirect(student)
    return render(request, "tracker/form_page.html", {
        "form": form,
        "title": f"Edit {student.name}" if student else "Add student",
        "cancel_url": student.get_absolute_url() if student else reverse("tracker:student_list"),
        "class_names": ClassOrder.ordered_class_names(),
    })


@require_POST
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    student.delete()
    messages.success(request, f"Deleted {student.name} and all their purchases and payments.")
    return redirect("tracker:student_list")


def _students_for(request):
    class_name = request.GET.get("class_name")
    students = Student.objects.all()
    if class_name:
        students = students.filter(class_name=class_name)
    return students


def purchase_form(request, pk=None):
    purchase = get_object_or_404(Purchase, pk=pk) if pk else None
    initial = {"student": request.GET.get("student")} if not purchase else {}
    form = PurchaseForm(request.POST or None, instance=purchase, initial=initial,
                        students=None if purchase else _students_for(request))
    default_next = purchase.student.get_absolute_url() if purchase else None
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Purchase saved: {saved.material} × {saved.quantity} = £{saved.total_cost}.")
        return redirect(_next_url(request, default_next or saved.student.get_absolute_url()))
    return render(request, "tracker/purchase_form.html", {
        "form": form,
        "title": "Edit purchase" if purchase else "Record purchase",
        "purchase": purchase,
        "next": _next_url(request, default_next or reverse("tracker:dashboard")),
    })


def price_preview(request):
    """HTMX partial: live price breakdown while filling in the purchase form."""
    material = Material.objects.filter(pk=request.GET.get("material") or None).first()
    try:
        quantity = Decimal(request.GET.get("quantity") or "0")
    except InvalidOperation:
        quantity = ZERO
    context = {"material": material, "quantity": quantity}
    if material:
        context["total"] = money(quantity * material.final_price)
    return render(request, "tracker/partials/price_preview.html", context)


@require_POST
def purchase_delete(request, pk):
    purchase = get_object_or_404(Purchase.objects.select_related("student", "material"), pk=pk)
    student = purchase.student
    undo.remember(request, f"Deleted {purchase.material} × {purchase.quantity:g} for {student}.", deleted=[purchase])
    purchase.delete()
    if request.htmx:
        return HttpResponse(headers={"HX-Refresh": "true"})
    return redirect(_next_url(request, student.get_absolute_url()))


def payment_form(request, pk=None):
    payment = get_object_or_404(Payment, pk=pk) if pk else None
    initial = {"student": request.GET.get("student")} if not payment else {}
    form = PaymentForm(request.POST or None, instance=payment, initial=initial,
                       students=None if payment else _students_for(request))
    default_next = payment.student.get_absolute_url() if payment else None
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Payment of £{saved.amount} from {saved.student} saved.")
        return redirect(_next_url(request, default_next or saved.student.get_absolute_url()))
    return render(request, "tracker/payment_form.html", {
        "form": form,
        "title": "Edit payment" if payment else "Record payment",
        "next": _next_url(request, default_next or reverse("tracker:dashboard")),
    })


def student_balance(request):
    """HTMX partial: show the chosen student's balance on the payment form."""
    student = Student.objects.with_balances().filter(pk=request.GET.get("student") or None).first()
    return render(request, "tracker/partials/balance.html", {"student": student})


@require_POST
def payment_delete(request, pk):
    payment = get_object_or_404(Payment.objects.select_related("student"), pk=pk)
    student = payment.student
    undo.remember(request, f"Deleted payment of £{payment.amount} from {student}.", deleted=[payment])
    payment.delete()
    if request.htmx:
        return HttpResponse(headers={"HX-Refresh": "true"})
    return redirect(_next_url(request, student.get_absolute_url()))


@require_POST
def undo_last(request):
    label = undo.undo(request, request.POST.get("id", ""))
    if label:
        messages.success(request, f"Undone: {label}")
    else:
        messages.error(request, "That can no longer be undone.")
    return redirect(_next_url(request, reverse("tracker:dashboard")))


# ---------- Class mode (student-facing: student prices only, no costs or other balances) ----------

def _class_url(class_name):
    return f"{reverse('tracker:class_mode')}?{urlencode({'class_name': class_name})}"


def class_mode(request):
    class_name = request.GET.get("class_name")
    students = Student.objects.filter(is_sales_channel=False)
    if class_name is None:
        counts = dict(students.values_list("class_name").annotate(n=Count("id")))
        classes = [(name, name, counts[name]) for name in ClassOrder.ordered_class_names() if name in counts]
        if counts.get(""):
            classes.append(("", NO_CLASS, counts[""]))
        return render(request, "tracker/class_mode_index.html", {"classes": classes})
    return render(request, "tracker/class_mode.html", {
        "class_name": class_name,
        "class_label": class_name or NO_CLASS,
        "students": students.filter(class_name=class_name),
    })


def _quick_materials():
    active = Material.objects.filter(is_active=True).select_related("category")
    favourites = active.filter(is_favourite=True)
    if favourites.exists():
        return favourites
    return active.annotate(n=Count("purchases")).order_by("-n", "name")[:12]


def class_basket(request, pk):
    student = get_object_or_404(Student.objects.with_balances(), pk=pk)
    back = _class_url(student.class_name)
    if request.method == "POST":
        materials = {m.pk: m for m in Material.objects.filter(is_active=True)}
        try:
            when = date.fromisoformat(request.POST.get("purchase_date") or "")
        except ValueError:
            when = timezone.localdate()
        project = Project.objects.filter(pk=request.POST.get("project") or None).first()
        created = []
        with transaction.atomic():
            for key, value in request.POST.items():
                if not key.startswith("qty_"):
                    continue
                try:
                    material, quantity = materials.get(int(key[4:])), Decimal(value).quantize(Decimal("0.01"))
                except (ValueError, InvalidOperation):
                    continue
                if material is None or quantity <= 0:
                    continue
                purchase = Purchase(student=student, material=material, quantity=quantity,
                                    purchase_date=when, project=project)
                purchase.set_price(reprice=True)
                purchase.save()
                created.append(purchase)
        if created:
            total = sum((p.total_cost for p in created), ZERO)
            items = f"{len(created)} item{'s' if len(created) != 1 else ''}"
            undo.remember(request, f"Added {items} (£{total}) for {student}.", created=created)
        else:
            messages.error(request, f"Nothing was added for {student} – the basket was empty.")
        return redirect(back)
    return render(request, "tracker/class_basket.html", {
        "student": student,
        "back": back,
        "class_label": student.class_name or NO_CLASS,
        "quick": _quick_materials(),
        "projects": Project.objects.all(),
        "today": timezone.localdate(),
        "owed": -student.balance if student.balance < 0 else ZERO,
    })


def class_search(request):
    words = request.GET.get("q", "").split()
    materials = Material.objects.none()
    if words:
        materials = Material.objects.filter(is_active=True).select_related("category")
        for word in words:
            materials = materials.filter(Q(name__icontains=word) | Q(category__name__icontains=word))
        materials = materials[:12]
    return render(request, "tracker/partials/material_tiles.html", {"materials": materials, "searching": bool(words)})


@require_POST
def settle_up(request, pk):
    student = get_object_or_404(Student.objects.with_balances(), pk=pk)
    method = request.POST.get("method")
    if method not in Payment.Method.values:
        method = Payment.Method.CASH
    if student.balance >= 0:
        messages.error(request, f"{student} doesn't owe anything.")
    else:
        payment = Payment.objects.create(student=student, amount=-student.balance, payment_method=method,
                                         notes="Settled up")
        undo.remember(request, f"{student} paid £{payment.amount} by {method.lower()}.", created=[payment])
    return redirect(_next_url(request, _class_url(student.class_name)))


def payments_report(request):
    form = PaymentFilterForm(request.GET or None)
    payments = Payment.objects.select_related("student")
    if form.is_valid():
        data = form.cleaned_data
        if data["group"] == "class":
            payments = payments.filter(student__is_sales_channel=False)
        elif data["group"] == "sales":
            payments = payments.filter(student__is_sales_channel=True)
        if data["student"]:
            payments = payments.filter(student=data["student"])
        if data["start"]:
            payments = payments.filter(payment_date__gte=data["start"])
        if data["end"]:
            payments = payments.filter(payment_date__lte=data["end"])
    context = {"form": form, "payments": payments, "totals": _method_totals(payments)}
    template = "tracker/partials/payments_table.html" if request.htmx else "tracker/payments_report.html"
    return render(request, template, context)


def _profit_row(label, sales, cost, **extra):
    sales, cost = sales or ZERO, cost or ZERO
    profit = sales - cost
    margin = (profit / sales * 100) if sales else None
    return {"label": label, "sales": sales, "cost": cost, "profit": profit, "margin": margin, **extra}


def profit_report(request):
    """Private: what students paid for materials minus what those materials cost the studio."""
    form = DateRangeForm(request.GET or None)
    purchases = Purchase.objects.all()
    if form.is_valid():
        if form.cleaned_data["start"]:
            purchases = purchases.filter(purchase_date__gte=form.cleaned_data["start"])
        if form.cleaned_data["end"]:
            purchases = purchases.filter(purchase_date__lte=form.cleaned_data["end"])
    sums = {"sales": Sum("total_cost"), "cost": Sum("cost_total")}

    total = purchases.aggregate(**sums)
    by_month = [
        _profit_row(r["month"], r["sales"], r["cost"])
        for r in purchases.annotate(month=TruncMonth("purchase_date")).values("month").annotate(**sums).order_by("-month")
    ]
    by_class = sorted(
        (_profit_row(
            "Sales channels" if r["student__is_sales_channel"] else (r["student__class_name"] or NO_CLASS),
            r["sales"], r["cost"])
         for r in purchases.values("student__class_name", "student__is_sales_channel").annotate(**sums)),
        key=lambda row: -row["profit"],
    )
    by_material = sorted(
        (_profit_row(r["material__name"], r["sales"], r["cost"], quantity=r["quantity"], unit=r["material__unit_type"])
         for r in purchases.values("material__name", "material__unit_type").annotate(quantity=Sum("quantity"), **sums)),
        key=lambda row: -row["profit"],
    )
    return render(request, "tracker/profit_report.html", {
        "form": form,
        "total": _profit_row("Total", total["sales"], total["cost"]),
        "by_month": by_month,
        "by_class": by_class,
        "by_material": by_material,
        "n_estimated": purchases.filter(cost_is_estimate=True).count(),
        "n_purchases": purchases.count(),
    })


def material_list(request):
    materials = Material.objects.select_related("category").annotate(n_purchases=Count("purchases"))
    show_inactive = request.GET.get("inactive") == "1"
    if not show_inactive:
        materials = materials.filter(is_active=True)
    return render(request, "tracker/material_list.html", {
        "materials": materials,
        "show_inactive": show_inactive,
        "has_supplier_links": Material.objects.filter(is_active=True).exclude(supplier_url="").exists(),
        "recent_changes": PriceChange.objects.select_related("material")[:8],
    })


def material_form(request, pk=None):
    material = get_object_or_404(Material, pk=pk) if pk else None
    form = MaterialForm(request.POST or None, instance=material)
    if request.method == "POST" and form.is_valid():
        old = Material.objects.filter(pk=pk).values("base_price", "weight_per_unit").first() if pk else None
        saved = form.save()
        if old and (old["base_price"] != saved.base_price or old["weight_per_unit"] != saved.weight_per_unit):
            PriceChange.objects.create(
                material=saved, old_price=old["base_price"], new_price=saved.base_price,
                old_weight=old["weight_per_unit"], new_weight=saved.weight_per_unit, source="manual",
            )
        messages.success(request, f"Saved {saved.name}.")
        return redirect("tracker:material_list")
    return render(request, "tracker/material_form.html", {
        "form": form,
        "material": material,
        "category_names": Category.objects.values_list("name", flat=True),
    })


def material_price_calc(request):
    """HTMX partial: live cost/selling price while editing a material."""
    def number(name, default="0"):
        try:
            return Decimal(request.GET.get(name) or default)
        except InvalidOperation:
            return Decimal(default)

    material = Material(
        pricing_type=request.GET.get("pricing_type") or Material.PricingType.FIXED,
        unit_type=request.GET.get("unit_type") or "item",
        base_price=number("base_price"),
        pack_quantity=number("pack_quantity", "1"),
        weight_per_unit=number("weight_per_unit") or None,
        markup_percentage=number("markup_percentage"),
    )
    return render(request, "tracker/partials/material_price_calc.html", {"material": material})


@require_POST
def material_fetch(request):
    """HTMX: fill the price (and item weight) fields from the supplier link."""
    url = request.POST.get("supplier_url", "").strip()
    pricing_type = request.POST.get("pricing_type") or Material.PricingType.FIXED
    quote = suppliers.fetch_quote(url, pricing_type) if url else suppliers.Quote(error="Paste the supplier link first.")
    form = MaterialForm(initial={"base_price": quote.price, "weight_per_unit": quote.weight_per_unit})
    response = render(request, "tracker/partials/material_fetch.html", {"form": form, "quote": quote})
    response["HX-Trigger-After-Settle"] = "fetched"
    return response


@require_POST
def material_toggle(request, pk):
    material = get_object_or_404(Material, pk=pk)
    material.is_active = not material.is_active
    material.save(update_fields=["is_active", "last_updated"])
    state = "shown in" if material.is_active else "hidden from"
    messages.success(request, f"{material.name} is now {state} the purchase list.")
    return redirect(_next_url(request, reverse("tracker:material_list")))


@require_POST
def material_delete(request, pk):
    material = get_object_or_404(Material, pk=pk)
    try:
        material.delete()
        messages.success(request, f"Deleted {material.name}.")
    except ProtectedError:
        messages.error(request, f"{material.name} has purchases recorded, so it can't be deleted – hide it instead.")
    return redirect("tracker:material_list")


def price_check(request):
    """HTMX partial: fetch supplier prices and show old → new for confirmation (nothing is saved yet)."""
    materials = Material.objects.exclude(supplier_url="").select_related("category")
    if request.GET.get("id"):
        materials = materials.filter(pk=request.GET["id"])
    else:
        materials = materials.filter(is_active=True)
    materials = list(materials)
    quotes = suppliers.fetch_quotes(materials)
    rows = []
    for m in materials:
        q = quotes[m.pk]
        new_weight = q.weight_per_unit if q.weight_per_unit is not None else m.weight_per_unit
        changed = q.price is not None and (q.price != m.base_price or new_weight != m.weight_per_unit)
        new_final = None
        if q.price is not None:
            preview = Material(pricing_type=m.pricing_type, base_price=q.price, pack_quantity=m.pack_quantity,
                               weight_per_unit=new_weight, markup_percentage=m.markup_percentage)
            new_final = preview.final_price
        rows.append({"material": m, "quote": q, "new_weight": new_weight, "changed": changed, "new_final": new_final})
    return render(request, "tracker/partials/price_check.html", {
        "rows": rows,
        "n_changed": sum(r["changed"] for r in rows),
        "n_failed": sum(bool(r["quote"].error) for r in rows),
        "includes_vat": settings.SUPPLIER_PRICES_INCLUDE_VAT,
    })


@require_POST
def price_apply(request):
    updated = 0
    with transaction.atomic():
        for pk in request.POST.getlist("apply"):
            material = Material.objects.filter(pk=pk).first()
            try:
                new_price = Decimal(request.POST[f"price_{pk}"])
                new_weight = Decimal(request.POST[f"weight_{pk}"]) if request.POST.get(f"weight_{pk}") else material.weight_per_unit
            except (KeyError, InvalidOperation, AttributeError):
                continue
            if new_price <= 0:
                continue
            PriceChange.objects.create(
                material=material, old_price=material.base_price, new_price=new_price,
                old_weight=material.weight_per_unit, new_weight=new_weight,
            )
            material.base_price, material.weight_per_unit = new_price, new_weight
            material.save(update_fields=["base_price", "weight_per_unit", "last_updated"])
            updated += 1
    messages.success(request, f"Updated {updated} price{'s' if updated != 1 else ''}. Past purchases keep the price they were charged.")
    return redirect("tracker:material_list")


def silver_price(request):
    """HTMX partial for the dashboard card; refreshes once a day or on demand."""
    latest = SilverPrice.objects.first()
    stale = latest is None or timezone.localtime(latest.fetched_at).date() != timezone.localdate()
    error = ""
    if stale or request.GET.get("refresh"):
        try:
            latest = SilverPrice.objects.create(price_per_kg=suppliers.fetch_silver_price_per_kg())
        except suppliers.SupplierError as exc:
            error = str(exc)
    previous = SilverPrice.objects.filter(fetched_at__date__lt=timezone.localdate()).first() if latest else None
    return render(request, "tracker/partials/silver_price.html", {"silver": latest, "previous": previous, "error": error})


def class_reorder(request):
    if request.method == "POST":
        names = [n for n in request.POST.getlist("class_name") if n]
        with transaction.atomic():
            ClassOrder.objects.all().delete()
            ClassOrder.objects.bulk_create(ClassOrder(class_name=n, sort_order=i) for i, n in enumerate(names))
        return render(request, "tracker/partials/saved.html")
    return render(request, "tracker/class_reorder.html", {"class_names": ClassOrder.ordered_class_names()})


def material_arrange(request):
    categories = list(Category.objects.all())
    materials = Material.objects.select_related("category")
    groups = [(c, [m for m in materials if m.category_id == c.pk]) for c in categories]
    uncategorised = [m for m in materials if m.category_id is None]
    if uncategorised:
        groups.append((None, uncategorised))
    return render(request, "tracker/material_arrange.html", {"categories": categories, "groups": groups})


@require_POST
def category_order(request):
    with transaction.atomic():
        for i, pk in enumerate(request.POST.getlist("category")):
            Category.objects.filter(pk=pk).update(sort_order=i)
    return render(request, "tracker/partials/saved.html")


@require_POST
def material_order(request):
    with transaction.atomic():
        for i, pk in enumerate(request.POST.getlist("material")):
            Material.objects.filter(pk=pk).update(sort_order=i)
    return render(request, "tracker/partials/saved.html")


def project_list(request):
    projects = Project.objects.annotate(
        total_cost=Sum("purchases__total_cost"),
        n_students=Count("purchases__student", distinct=True),
    )
    rows = []
    for project in projects:
        purchases = project.purchases.select_related("student", "material")
        students = sorted({p.student for p in purchases}, key=lambda s: s.name)
        materials = (
            project.purchases.values("material__name", "material__unit_type")
            .annotate(quantity=Sum("quantity"), cost=Sum("total_cost"))
            .order_by("material__name")
        )
        total = project.total_cost or ZERO
        rows.append({
            "project": project,
            "students": students,
            "materials": materials,
            "total": total,
            "average": money(total / project.n_students) if project.n_students else None,
        })
    return render(request, "tracker/project_list.html", {"rows": rows})


def project_form(request, pk=None):
    project = get_object_or_404(Project, pk=pk) if pk else None
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Saved project “{saved.name}”.")
        return redirect("tracker:project_list")
    return render(request, "tracker/form_page.html", {
        "form": form,
        "title": f"Edit {project.name}" if project else "New project",
        "cancel_url": reverse("tracker:project_list"),
    })


@require_POST
def project_delete(request, pk):
    project = get_object_or_404(Project, pk=pk)
    project.delete()
    messages.success(request, f"Deleted project “{project.name}”. Its purchases are kept.")
    return redirect("tracker:project_list")
