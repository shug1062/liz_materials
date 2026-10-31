import sqlite3
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.management import call_command
from django.db import transaction
from django.db.models import Count, F, ProtectedError, Q, Sum
from django.forms.models import model_to_dict
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import contacts_import, margins, silver, statements, suppliers, undo
from . import reports as reports_lib
from .forms import (
    BackupSettingsForm, DateRangeForm, MaterialForm, PaymentFilterForm, PaymentForm, ProjectForm, PurchaseForm,
    SilverPriceForm, StudentForm,
    StudioClassForm, TermDatesForm,
)
from .models import (
    ZERO, Category, Material, Payment, PriceChange, Project, Purchase, SilverPrice, Student, StudioClass, StudioSettings,
    money,
)

NO_CLASS = "No class assigned"


def _class_students_url(class_name):
    """The Students page for one class – where Liz returns after recording something for one of its students."""
    url = reverse("tracker:student_list")
    return f"{url}?{urlencode({'class_name': class_name})}" if class_name else url


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
        "bank": totals.get(Payment.Method.BANK_TRANSFER, ZERO),
        "other": totals.get(Payment.Method.OTHER, ZERO),
        "methods": [(m.label, totals.get(m, ZERO)) for m in Payment.Method],
        "total": sum(totals.values(), ZERO),
    }


def dashboard(request):
    class_students = Student.objects.with_balances().filter(is_sales_channel=False)
    balances = [s.balance for s in class_students]
    class_payments = Payment.objects.filter(student__is_sales_channel=False)
    channels = Student.objects.filter(is_sales_channel=True)
    channel_totals = [(c, _method_totals(c.payments.all())) for c in channels]

    class_counts = dict(
        Student.objects.active().filter(is_sales_channel=False)
        .exclude(class_name="")
        .values_list("class_name")
        .annotate(n=Count("id"))
    )
    classes = [(name, class_counts[name]) for name in StudioClass.ordered_class_names(include_finished=False)
               if name in class_counts]

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


def settings_page(request):
    studio_settings, _ = StudioSettings.objects.get_or_create(pk=1)
    if request.method == "POST":
        form = BackupSettingsForm(request.POST)
        if form.is_valid():
            studio_settings.backup_directory = form.cleaned_data["backup_directory"]
            studio_settings.save(update_fields=["backup_directory"])
            if studio_settings.backup_directory:
                try:
                    call_command("backup_db")
                except (OSError, sqlite3.Error) as error:
                    messages.error(
                        request,
                        f"Backup folder saved, but the backup could not be copied there: {error}",
                    )
                else:
                    messages.success(request, "Backup folder saved and a backup was copied there.")
            else:
                messages.success(request, "OneDrive backup copy turned off.")
            return redirect("tracker:settings")
    else:
        form = BackupSettingsForm(initial={
            "backup_directory": (
                studio_settings.backup_directory
                if studio_settings.backup_directory is not None
                else settings.BACKUP_COPY_DIR or ""
            )
        })
    return render(request, "tracker/settings.html", {
        "studio_lan_ip": settings.STUDIO_LAN_IP,
        "studio_hostname": settings.STUDIO_HOSTNAME,
        "backup_form": form,
        "has_backup_directory": bool(
            studio_settings.backup_directory if studio_settings.backup_directory is not None
            else settings.BACKUP_COPY_DIR
        ),
        "last_backup_date": studio_settings.last_backup_date,
        "data_dir": settings.DATA_DIR,
    })


def student_list(request):
    selected = request.GET.get("class_name", "")
    students = Student.objects.with_balances().active().filter(is_sales_channel=False)
    if selected:
        students = students.filter(class_name=selected)
    groups = {}
    for s in students:
        s.back_url = _class_students_url(s.class_name)
        groups.setdefault(s.class_name or NO_CLASS, []).append(s)
    order = StudioClass.ordered_class_names() + [NO_CLASS]
    grouped = []
    for name in order:
        if name in groups:
            members = groups[name]
            grouped.append({
                "name": name,
                "students": members,
                "owed": -sum((s.balance for s in members if s.balance < 0), ZERO),
                "credit": sum((s.balance for s in members if s.balance > 0), ZERO),
                "open": True,
            })
    return render(request, "tracker/student_list.html", {
        "groups": grouped,
        "selected": selected,
        "no_class": NO_CLASS,
        "channels": Student.objects.with_balances().filter(is_sales_channel=True),
        "n_archived": Student.objects.filter(is_archived=True).count(),
    })


def archived_students(request):
    q = request.GET.get("q", "").strip()
    students = Student.objects.with_balances().filter(is_archived=True)
    if q:
        students = students.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(class_name__icontains=q))
    template = "tracker/partials/archived_rows.html" if request.htmx else "tracker/archived_students.html"
    return render(request, template, {"students": students, "q": q})


@require_POST
def student_archive(request, pk):
    """Archive or restore a single student (with Undo)."""
    student = get_object_or_404(Student, pk=pk)
    undo.remember(request, f"{'Restored' if student.is_archived else 'Archived'} {student}.", restore=[student])
    student.is_archived = not student.is_archived
    student.archived_at = timezone.now() if student.is_archived else None
    student.save(update_fields=["is_archived", "archived_at"])
    return redirect(_next_url(request, student.get_absolute_url()))


def student_merge(request, pk):
    """Fold a duplicate record into another student: purchases and payments move across, then it's removed."""
    student = get_object_or_404(Student.objects.with_balances(), pk=pk)
    others = Student.objects.with_balances().exclude(pk=student.pk).order_by("is_archived", "name")
    # The page offers same-name radio buttons and a full drop-down; use whichever was filled in.
    chosen = next((v for v in (request.POST or request.GET).getlist("into") if v.isdigit()), None)
    into = others.filter(pk=chosen).first() if chosen else None
    if request.method == "POST" and into:
        purchases, payments = list(student.purchases.all()), list(student.payments.all())
        with transaction.atomic():
            undo.remember(request, f"Merged {student} ({student.class_name or 'no class'}) into {into}.",
                          restore=[Student.objects.get(pk=into.pk), student, *purchases, *payments])
            student.purchases.update(student=into)
            student.payments.update(student=into)
            into.email = into.email or student.email
            into.phone = into.phone or student.phone
            if student.notes:
                into.notes = f"{into.notes}\n{student.notes}".strip()
            into.save(update_fields=["email", "phone", "notes"])
            student.delete()
        return redirect(into)
    key = " ".join(student.name.split()).lower()
    same_name = [s for s in others if " ".join(s.name.split()).lower() == key]
    return render(request, "tracker/student_merge.html", {
        "student": student,
        "same_name": same_name,
        "others": others,
        "into": into,
    })


IMPORT_SESSION_KEY = "contact_import"


def student_import(request):
    """Fill in emails and phone numbers (and add new students) from an attendee export, e.g. a Wix CSV.

    Nothing changes until the preview is confirmed; the parsed file waits in the session in between.
    """
    if request.method == "POST" and "apply" in request.POST:
        return _apply_import(request)
    people, error = None, ""
    if request.method == "POST":
        upload = request.FILES.get("file")
        if not upload:
            error = "Choose a CSV file first."
        else:
            try:
                people = contacts_import.read_people(upload.read(contacts_import.MAX_BYTES + 1))
            except ValueError as exc:
                error = str(exc)
            else:
                people = contacts_import.match(people, Student.objects.filter(is_sales_channel=False)
                                               .order_by("is_archived", "name"))
                request.session[IMPORT_SESSION_KEY] = [
                    {"name": p.name, "email": p.email, "phone": p.phone} for p in people
                ]
                if not people:
                    error = "No people found in that file."
    return render(request, "tracker/student_import.html", {
        "people": people,
        "error": error,
        "class_names": StudioClass.ordered_class_names(include_finished=False),
    })


def _apply_import(request):
    rows = request.session.pop(IMPORT_SESSION_KEY, None)
    if rows is None:
        messages.error(request, "That import has expired – please upload the file again.")
        return redirect("tracker:student_import")
    new_class = " ".join(request.POST.get("new_class", "").split())[:100]
    created, before, n_updated = [], [], 0
    with transaction.atomic():
        for i, row in enumerate(rows):
            action = request.POST.get(f"action_{i}", "skip")
            if action == "new":
                created.append(Student.objects.create(name=row["name"][:200], email=row["email"],
                                                      phone=row["phone"][:50], class_name=new_class))
                continue
            student = Student.objects.filter(pk=action).first() if action.isdigit() else None
            if student is None:
                continue
            original = Student.objects.get(pk=student.pk)
            if row["email"] and not student.email:
                student.email = row["email"]
            if row["phone"] and not student.phone:
                student.phone = row["phone"][:50]
            if request.POST.get(f"rename_{i}"):
                student.name = row["name"][:200]
            if (student.email, student.phone, student.name) != (original.email, original.phone, original.name):
                before.append(original)
                student.save(update_fields=["email", "phone", "name"])
                n_updated += 1
        if created or before:
            undo.remember(request, f"Imported contacts: updated {n_updated}, added {len(created)} new.",
                          created=created, restore=before)
        else:
            messages.success(request, "Nothing needed changing.")
    return redirect("tracker:student_list")


def student_detail(request, pk):
    student = get_object_or_404(statements.with_history(Student.objects.with_balances()), pk=pk)
    return render(request, "tracker/student_detail.html", {
        "student": student,
        "purchases": student.purchases.select_related("material", "project"),
        "payments": student.payments.all(),
        "statement": statements.statement_for(student),
    })


def student_statement(request, pk):
    """Print-friendly statement: what's owed, the items it covers, and the full account history."""
    student = get_object_or_404(statements.with_history(Student.objects.all()), pk=pk)
    history = sorted(
        [(p.purchase_date, p.material.name, p.quantity, p.material.unit_type, p.total_cost, None)
         for p in student.purchases.all()]
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
    owing = Student.objects.with_balances().filter(is_sales_channel=False, total_purchases__gt=F("total_payments"))
    rows = sorted((statements.statement_for(s) for s in statements.with_history(owing)), key=lambda st: -st.owed)
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
        "class_names": StudioClass.ordered_class_names(include_finished=False),
    })


@require_POST
def student_delete(request, pk):
    student = get_object_or_404(Student, pk=pk)
    student.delete()
    messages.success(request, f"Deleted {student.name} and all their purchases and payments.")
    return redirect("tracker:student_list")


def _students_for(request, include_archived=False):
    class_name = request.GET.get("class_name")
    # Archived students stay selectable for payments (settling old debts) but sort last.
    students = Student.objects.order_by("is_archived", "name") if include_archived else Student.objects.active()
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
        return redirect(_next_url(request, default_next or _class_students_url(saved.student.class_name)))
    return render(request, "tracker/purchase_form.html", {
        "form": form,
        "title": "Edit purchase" if purchase else "Record purchase",
        "purchase": purchase,
        "next": _next_url(request, default_next or reverse("tracker:dashboard")),
    })


def price_preview(request):
    """HTMX partial: live price breakdown while filling in the purchase form."""
    material_id = request.GET.get("material", "")
    material = Material.objects.filter(pk=material_id).first() if material_id.isdigit() else None
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
    undo.remember(request, f"Deleted {purchase.material} × {purchase.quantity:g} for {student}.", restore=[purchase])
    purchase.delete()
    if request.htmx:
        return HttpResponse(headers={"HX-Refresh": "true"})
    return redirect(_next_url(request, student.get_absolute_url()))


def payment_form(request, pk=None):
    payment = get_object_or_404(Payment, pk=pk) if pk else None
    initial = {"student": request.GET.get("student")} if not payment else {}
    form = PaymentForm(request.POST or None, instance=payment, initial=initial,
                       students=None if payment else _students_for(request, include_archived=True))
    default_next = payment.student.get_absolute_url() if payment else None
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Payment of £{saved.amount} from {saved.student} saved.")
        return redirect(_next_url(request, default_next or _class_students_url(saved.student.class_name)))
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
    undo.remember(request, f"Deleted payment of £{payment.amount} from {student}.", restore=[payment])
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
    students = Student.objects.active().filter(is_sales_channel=False)
    if class_name is None:
        counts = dict(students.values_list("class_name").annotate(n=Count("id")))
        classes = [(name, name, counts[name]) for name in StudioClass.ordered_class_names(include_finished=False)
                   if name in counts]
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
        "methods": Payment.Method.choices,
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


@require_POST
def class_payment(request, pk):
    student = get_object_or_404(Student, pk=pk)
    data = request.POST.copy()
    data["student"] = student.pk
    if not data.get("payment_date"):
        data["payment_date"] = timezone.localdate().isoformat()
    form = PaymentForm(data, students=Student.objects.filter(pk=student.pk))
    if form.is_valid():
        payment = form.save()
        undo.remember(request, f"{student} paid £{payment.amount} by {payment.payment_method.lower()}.", created=[payment])
        return redirect(_class_url(student.class_name))
    errors = " ".join(e for field in form.errors.values() for e in field)
    messages.error(request, f"Payment not saved: {errors}")
    return redirect("tracker:class_basket", pk=student.pk)


def payments_report(request):
    params = request.GET.copy()
    tax_start, tax_end = reports_lib.tax_year(timezone.localdate())
    if not params:
        params.update({"start": tax_start.isoformat(), "end": tax_end.isoformat()})
    form = PaymentFilterForm(params)
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
    context = {"form": form, "payments": payments, "totals": _method_totals(payments),
               "tax_year": f"{tax_start.year}/{str(tax_end.year)[2:]}"}
    template = "tracker/partials/payments_table.html" if request.htmx else "tracker/payments_report.html"
    return render(request, template, context)


def _profit_row(label, sales, cost, **extra):
    sales, cost = sales or ZERO, cost or ZERO
    profit = sales - cost
    margin = (profit / sales * 100) if sales else None
    return {"label": label, "sales": sales, "cost": cost, "profit": profit, "margin": margin, **extra}


def _report_range(request):
    form = DateRangeForm(request.GET or None)
    start = end = None
    if form.is_valid():
        start, end = form.cleaned_data["start"], form.cleaned_data["end"]
    return form, start, end


def reports(request):
    """Private: money received by month (cash/card), materials sold, cost and profit, with CSV exports."""
    form, start, end = _report_range(request)
    payments, all_purchases = reports_lib.filtered(start, end)
    purchases = all_purchases.filter(material__kind=Material.Kind.MATERIAL)
    sums = {"sales": Sum("total_cost"), "cost": Sum("cost_total")}

    total = purchases.aggregate(**sums)
    other_sales = dict(all_purchases.exclude(material__kind=Material.Kind.MATERIAL)
                       .values_list("material__kind").annotate(Sum("total_cost")))
    income = _method_totals(payments)
    silver_only = request.GET.get("by_class") == "silver"
    class_purchases = purchases.filter(material__is_silver=True) if silver_only else purchases
    by_class = sorted(
        (_profit_row(
            "Sales channels" if r["student__is_sales_channel"] else (r["class_name"] or NO_CLASS),
            r["sales"], r["cost"])
         for r in class_purchases.values("class_name", "student__is_sales_channel").annotate(**sums)),
        key=lambda row: -row["profit"],
    )
    scope_query = request.GET.copy()
    scope_links = []
    for value, label in [("", "All materials"), ("silver", "Silver only")]:
        scope_query["by_class"] = value
        scope_links.append((label, f"?{scope_query.urlencode()}#by-class", silver_only == bool(value)))
    silver_sales = purchases.filter(material__is_silver=True)
    by_material = sorted(
        (_profit_row(r["material__name"], r["sales"], r["cost"], quantity=r["quantity"], unit=r["material__unit_type"])
         for r in purchases.values("material__name", "material__unit_type").annotate(quantity=Sum("quantity"), **sums)),
        key=lambda row: -row["profit"],
    )
    return render(request, "tracker/reports.html", {
        "form": form,
        "start": start,
        "end": end,
        "presets": reports_lib.presets(timezone.localdate()),
        "query": request.GET.urlencode(),
        "income": income,
        "other_income": income["total"] - income["cash"] - income["card"],
        "total": _profit_row("Total", total["sales"], total["cost"]),
        "lesson_fees": other_sales.get(Material.Kind.LESSON) or ZERO,
        "orders_at_cost": other_sales.get(Material.Kind.ORDER) or ZERO,
        "by_month": reports_lib.monthly(payments, all_purchases),
        "by_class": by_class,
        "scope_links": scope_links,
        "silver_only": silver_only,
        "n_silver_rated": silver_sales.exclude(silver_rate=None).count(),
        "n_silver_unrated": silver_sales.filter(silver_rate=None).count(),
        "by_material": by_material,
        "n_estimated": purchases.filter(cost_is_estimate=True).count(),
        "n_purchases": purchases.count(),
    })


def reports_csv(request, kind):
    _, start, end = _report_range(request)
    payments, purchases = reports_lib.filtered(start, end)
    period = f"{start or 'start'}-to-{end or timezone.localdate()}"
    if kind == "payments":
        return reports_lib.csv_response(f"silverbird-payments-{period}.csv", reports_lib.PAYMENTS_HEADER,
                                        reports_lib.payments_csv_rows(payments))
    if kind == "sales":
        return reports_lib.csv_response(f"silverbird-materials-sold-{period}.csv", reports_lib.SALES_HEADER,
                                        reports_lib.sales_csv_rows(purchases))
    rows = reports_lib.monthly(payments, purchases)
    return reports_lib.csv_response(f"silverbird-monthly-{period}.csv", reports_lib.MONTHLY_HEADER,
                                    reports_lib.monthly_csv_rows(rows))


def material_list(request):
    materials = Material.objects.select_related("category").annotate(n_purchases=Count("purchases"))
    show_inactive = request.GET.get("inactive") == "1"
    if not show_inactive:
        materials = materials.filter(is_active=True)
    materials = list(materials)
    flags = margins.flag_materials([m for m in materials if m.is_active])
    threshold = Decimal(settings.THIN_MARGIN_PERCENT)
    for m in materials:
        m.margin_flags = flags.get(m.pk, [])
        m.low_markup = bool(m.margin_flags) and not m.markup_ok and margins.margin_percent(m.markup_percentage) < threshold
    return render(request, "tracker/material_list.html", {
        "materials": materials,
        "flagged": [m for m in materials if m.margin_flags],
        "n_low_markup": sum(m.low_markup for m in materials),
        "thin_margin": settings.THIN_MARGIN_PERCENT,
        "show_inactive": show_inactive,
        "has_supplier_links": Material.objects.filter(is_active=True).exclude(supplier_url="").exists(),
        "recent_changes": PriceChange.objects.select_related("material")[:8],
    })


@require_POST
def material_markup_ok(request):
    """Stop flagging deliberately low markups (with Undo)."""
    ids = [int(pk) for pk in request.POST.getlist("material") if pk.isdigit()]
    materials = list(Material.objects.filter(pk__in=ids, markup_ok=False))
    if materials:
        label = materials[0].name if len(materials) == 1 else f"{len(materials)} materials"
        undo.remember(request, f"Marked the low markup on {label} as on purpose.", restore=materials)
        Material.objects.filter(pk__in=[m.pk for m in materials]).update(markup_ok=True)
    return redirect("tracker:material_list")


def material_silver(request):
    """Tick which materials are silver, a whole category at a time; suggestions start ticked but aren't saved."""
    materials = list(Material.objects.filter(kind=Material.Kind.MATERIAL).select_related("category"))
    if request.method == "POST":
        ticked = {int(pk) for pk in request.POST.getlist("silver") if pk.isdigit()}
        changed = [m for m in materials if m.is_silver != (m.pk in ticked)]
        newly_silver = [m for m in changed if m.pk in ticked]
        with transaction.atomic():
            undo.remember(
                request, f"Updated silver ticks on {len(changed)} material{'s' if len(changed) != 1 else ''}.",
                restore=changed + list(Purchase.objects.filter(material__in=newly_silver)),
            )
            for m in changed:
                m.is_silver = m.pk in ticked
            Material.objects.bulk_update(changed, ["is_silver"])
            silver.recost(newly_silver)
        return redirect("tracker:material_list")
    for m in materials:
        m.suggested = not m.is_silver and silver.looks_like_silver(m)
    return render(request, "tracker/material_silver.html", {
        "materials": materials,
        "n_suggested": sum(m.suggested for m in materials),
    })


def material_form(request, pk=None):
    material = get_object_or_404(Material, pk=pk) if pk else None
    copy_id = request.GET.get("copy", "")
    source = Material.objects.filter(pk=copy_id).first() if not material and copy_id.isdigit() else None
    initial = {}
    if source:
        initial = model_to_dict(source, fields=[f for f in MaterialForm.Meta.fields if f != "category_name"])
        initial.update(name=f"{source.name} (copy)", category_name=source.category.name if source.category else "")
    form = MaterialForm(request.POST or None, instance=material, initial=initial)
    if request.method == "POST" and form.is_valid():
        old = Material.objects.filter(pk=pk or getattr(source, "pk", None)).first()
        saved = form.save(commit=False)
        price_changed = old is not None and any(
            getattr(old, f) != getattr(saved, f) for f in ("base_price", "pack_quantity", "weight_per_unit"))
        if price_changed and "price_date" not in form.changed_data:
            saved.price_date = timezone.localdate()
        if source:
            saved.sort_order = source.sort_order
        saved.save()
        if material and (old.base_price != saved.base_price or old.weight_per_unit != saved.weight_per_unit):
            PriceChange.objects.create(
                material=saved, old_price=old.base_price, new_price=saved.base_price,
                old_weight=old.weight_per_unit, new_weight=saved.weight_per_unit, source="manual",
            )
        if saved.is_silver:
            silver.recost([saved])
        messages.success(request, f"Saved {saved.name}.")
        return redirect("tracker:material_list")
    return render(request, "tracker/material_form.html", {
        "form": form,
        "material": material,
        "source": source,
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
    updated = []
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
            material.price_date = timezone.localdate()
            material.save(update_fields=["base_price", "weight_per_unit", "price_date", "last_updated"])
            updated.append(material)
        silver.recost([m for m in updated if m.is_silver])
    n = len(updated)
    messages.success(request, f"Updated {n} price{'s' if n != 1 else ''}. Past purchases keep the price they were charged.")
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


def price_history(request):
    """Every supplier/manual price change, plus the daily silver price readings."""
    changes = PriceChange.objects.select_related("material")
    material_id = request.GET.get("material", "")
    material = Material.objects.filter(pk=material_id).first() if material_id.isdigit() else None
    if material:
        changes = changes.filter(material=material)
    readings = list(SilverPrice.objects.all()[:180])
    for newer, older in zip(readings, readings[1:] + [None]):
        newer.change = (newer.price_per_kg - older.price_per_kg) / older.price_per_kg * 100 if older else None
    return render(request, "tracker/price_history.html", {
        "material": material,
        "silver_form": SilverPriceForm(),
        "changes": changes[:200],
        "silver": [] if material else readings,
    })


@require_POST
def silver_add(request):
    form = SilverPriceForm(request.POST)
    if form.is_valid():
        day, price = form.cleaned_data["day"], form.cleaned_data["price_per_kg"]
        reading = SilverPrice.objects.create(price_per_kg=price, source="manual",
                                             fetched_at=timezone.make_aware(datetime.combine(day, time(12))))
        undo.remember(request, f"Added silver at £{price}/kg on {day.day} {day:%b %Y}; silver sales from then on are re-costed.",
                      created=[reading])
    else:
        messages.error(request, "Silver price not saved: " + " ".join(e for errs in form.errors.values() for e in errs))
    return redirect("tracker:price_history")


@require_POST
def silver_delete(request, pk):
    reading = get_object_or_404(SilverPrice, pk=pk)
    undo.remember(request, f"Deleted silver price £{reading.price_per_kg}/kg from {reading.fetched_at:%d %b %Y}.",
                  restore=[reading])
    reading.delete()
    return redirect("tracker:price_history")


def class_reorder(request):
    if request.method == "POST":
        with transaction.atomic():
            for i, name in enumerate(request.POST.getlist("class_name")):
                StudioClass.objects.filter(name=name).update(sort_order=i)
        return render(request, "tracker/partials/saved.html")
    return redirect("tracker:class_list")


# ---------- Classes tab ----------

def _archive_candidates():
    """Active class students who aren't in a current or upcoming class (or have no class)."""
    keep = set(StudioClass.ordered_class_names(include_finished=False))
    return [s for s in Student.objects.with_balances().active().filter(is_sales_channel=False)
            if s.class_name not in keep]


def class_list(request):
    counts = dict(Student.objects.active().exclude(class_name="").values_list("class_name").annotate(n=Count("id")))
    classes = list(StudioClass.objects.all())
    for c in classes:
        c.n_students = counts.get(c.name, 0)
    return render(request, "tracker/class_list.html", {
        "classes": classes,
        "n_candidates": len(_archive_candidates()),
        "n_archived": Student.objects.filter(is_archived=True).count(),
    })


def class_dates(request):
    """Give several classes the same term dates at once; blank fields leave existing dates alone."""
    classes = list(StudioClass.objects.all())
    form = TermDatesForm(request.POST or None)
    chosen = {int(pk) for pk in request.POST.getlist("studio_class") if pk.isdigit()}
    if request.method == "POST" and form.is_valid():
        targets = [c for c in classes if c.pk in chosen]
        start, end = form.cleaned_data["start"], form.cleaned_data["end"]
        clashes = [c.name for c in targets if (start or c.start_date) and (end or c.end_date)
                   and (end or c.end_date) < (start or c.start_date)]
        if not targets:
            form.add_error(None, "Tick at least one class.")
        elif clashes:
            form.add_error(None, f"That would end {', '.join(clashes)} before {'it starts' if len(clashes) == 1 else 'they start'}.")
        else:
            undo.remember(request, f"Set term dates for {len(targets)} class{'es' if len(targets) != 1 else ''}.",
                          restore=targets)
            for c in targets:
                c.start_date, c.end_date = start or c.start_date, end or c.end_date
            StudioClass.objects.bulk_update(targets, ["start_date", "end_date"])
            return redirect("tracker:class_list")
    return render(request, "tracker/class_dates.html", {"classes": classes, "form": form, "chosen": chosen})


def class_form(request, pk=None):
    studio_class = get_object_or_404(StudioClass, pk=pk) if pk else None
    old_name = studio_class.name if studio_class else None
    form = StudioClassForm(request.POST or None, instance=studio_class)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            saved = form.save()
            if old_name and old_name != saved.name:
                Student.objects.filter(class_name=old_name).update(class_name=saved.name)
                Purchase.objects.filter(class_name=old_name).update(class_name=saved.name)
        messages.success(request, f"Saved {saved.name}.")
        return redirect(saved)
    return render(request, "tracker/form_page.html", {
        "form": form,
        "title": f"Edit {studio_class.name}" if studio_class else "New class",
        "cancel_url": studio_class.get_absolute_url() if studio_class else reverse("tracker:class_list"),
    })


def class_detail(request, pk):
    studio_class = get_object_or_404(StudioClass, pk=pk)
    return render(request, "tracker/class_detail.html", {
        "studio_class": studio_class,
        "students": Student.objects.with_balances().active().filter(class_name=studio_class.name),
        "candidates": _add_candidates(studio_class, ""),
    })


def _add_candidates(studio_class, q):
    """Students who could join this class: current students first, archived at the bottom."""
    students = Student.objects.filter(is_sales_channel=False).exclude(class_name=studio_class.name, is_archived=False)
    if q:
        students = students.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(class_name__icontains=q))
    return students.order_by("is_archived", "name")[:60]


def class_add_search(request, pk):
    studio_class = get_object_or_404(StudioClass, pk=pk)
    return render(request, "tracker/partials/class_candidates.html", {
        "studio_class": studio_class,
        "candidates": _add_candidates(studio_class, request.GET.get("q", "").strip()),
    })


@require_POST
def class_add_student(request, pk, student_pk):
    studio_class = get_object_or_404(StudioClass, pk=pk)
    student = get_object_or_404(Student, pk=student_pk)
    was = f" (was {student.class_name})" if student.class_name else ""
    undo.remember(request, f"Added {student} to {studio_class}{was}.", restore=[student])
    student.class_name, student.is_archived, student.archived_at = studio_class.name, False, None
    student.save()
    return redirect(studio_class)


def archive_students(request):
    """Preview, then (on POST) archive students not in a current or upcoming class. Never automatic."""
    candidates = _archive_candidates()
    if request.method == "POST":
        chosen = {int(pk) for pk in request.POST.getlist("student") if pk.isdigit()}
        to_archive = [s for s in candidates if s.pk in chosen]
        if to_archive:
            undo.remember(request, f"Archived {len(to_archive)} student{'s' if len(to_archive) != 1 else ''}.",
                          restore=to_archive)
            Student.objects.filter(pk__in=[s.pk for s in to_archive]).update(is_archived=True, archived_at=timezone.now())
        return redirect("tracker:class_list")
    return render(request, "tracker/archive_students.html", {"candidates": candidates})


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
    purchases_by_project = {}
    for p in Purchase.objects.filter(project__isnull=False).select_related("student", "material"):
        purchases_by_project.setdefault(p.project_id, []).append(p)
    rows = []
    for project in Project.objects.all():
        purchases = purchases_by_project.get(project.pk, [])
        students = sorted({p.student for p in purchases}, key=lambda s: s.name)
        materials = {}
        for p in purchases:
            m = materials.setdefault(p.material_id, {"material__name": p.material.name,
                                                     "material__unit_type": p.material.unit_type,
                                                     "quantity": ZERO, "cost": ZERO})
            m["quantity"] += p.quantity
            m["cost"] += p.total_cost
        total = sum((p.total_cost for p in purchases), ZERO)
        rows.append({
            "project": project,
            "students": students,
            "materials": sorted(materials.values(), key=lambda m: m["material__name"]),
            "total": total,
            "average": money(total / len(students)) if students else None,
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
