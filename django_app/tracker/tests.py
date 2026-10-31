import sqlite3
import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, call, patch

import keep_awake_windows
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from . import margins, reports, silver, statements, suppliers
from .models import (
    Category, Material, Payment, PriceChange, Project, Purchase, SilverPrice, Student, StudioClass, StudioSettings,
    estimated_unit_cost,
)


LEGACY_SCHEMA = """
    CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT, class_name TEXT, email TEXT, phone TEXT,
                           notes TEXT, is_sales_channel INTEGER, created_at TEXT);
    CREATE TABLE materials (id INTEGER PRIMARY KEY, name TEXT, category TEXT, unit_type TEXT, base_price REAL,
                            pack_quantity REAL, markup_percentage REAL, supplier TEXT, supplier_url TEXT,
                            is_active INTEGER, pricing_type TEXT, weight_per_unit REAL, notes TEXT);
    CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, description TEXT, created_at TEXT);
    CREATE TABLE purchases (id INTEGER PRIMARY KEY, student_id INTEGER, project_id INTEGER, material_id INTEGER,
                            quantity REAL, unit_price REAL, total_cost REAL, purchase_date TEXT, notes TEXT);
    CREATE TABLE payments (id INTEGER PRIMARY KEY, student_id INTEGER, amount REAL, payment_date TEXT,
                           payment_method TEXT, notes TEXT);
"""


def make_material(**kwargs):
    defaults = dict(name="Jump rings", base_price=Decimal("5.00"), pack_quantity=Decimal("50"),
                    markup_percentage=Decimal("20"))
    defaults.update(kwargs)
    return Material.objects.create(**defaults)


class PricingTests(TestCase):
    def test_fixed_pack_price(self):
        m = make_material()
        self.assertEqual(m.cost_per_item, Decimal("0.1"))
        self.assertEqual(m.final_price, Decimal("0.1200"))

    def test_per_gram_item_uses_weight(self):
        m = make_material(pricing_type=Material.PricingType.PER_GRAM_ITEM, base_price=Decimal("2.8894"),
                          weight_per_unit=Decimal("0.127"), pack_quantity=Decimal("1"), markup_percentage=Decimal("0"))
        self.assertEqual(m.final_price, Decimal("0.3670"))

    def test_per_gram_bulk_is_price_per_gram(self):
        m = make_material(pricing_type=Material.PricingType.PER_GRAM, base_price=Decimal("2.8894"),
                          pack_quantity=Decimal("1"), markup_percentage=Decimal("10"))
        self.assertEqual(m.final_price, Decimal("3.1783"))


class BalanceTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(name="Amy", class_name="Tue pm")
        self.material = make_material()

    def add_purchase(self, qty):
        p = Purchase(student=self.student, material=self.material, quantity=Decimal(qty))
        p.set_price(reprice=True)
        p.save()
        return p

    def test_balance_is_payments_minus_purchases(self):
        self.add_purchase("10")  # 10 × £0.12
        self.add_purchase("5")   # 5 × £0.12
        Payment.objects.create(student=self.student, amount=Decimal("1.00"))
        s = Student.objects.with_balances().get()
        self.assertEqual(s.total_purchases, Decimal("1.80"))
        self.assertEqual(s.total_payments, Decimal("1.00"))
        self.assertEqual(s.balance, Decimal("-0.80"))

    def test_balances_not_multiplied_by_joins(self):
        for _ in range(3):
            self.add_purchase("1")
        for _ in range(2):
            Payment.objects.create(student=self.student, amount=Decimal("1.00"))
        s = Student.objects.with_balances().get()
        self.assertEqual(s.total_purchases, Decimal("0.36"))
        self.assertEqual(s.total_payments, Decimal("2.00"))

    def test_edit_keeps_original_price_unless_material_changes(self):
        p = self.add_purchase("10")
        self.material.base_price = Decimal("10.00")
        self.material.save()
        p.quantity = Decimal("20")
        p.set_price(reprice=False)
        self.assertEqual(p.unit_price, Decimal("0.1200"))
        self.assertEqual(p.total_cost, Decimal("2.40"))

    def test_material_with_purchases_cannot_be_deleted(self):
        from django.db.models import ProtectedError
        self.add_purchase("1")
        with self.assertRaises(ProtectedError):
            self.material.delete()


class ViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("liz", password="test-pass-123")
        self.client.force_login(self.user)
        self.student = Student.objects.create(name="Amy", class_name="Tue pm")
        self.material = make_material(category=Category.objects.create(name="Findings"))

    def test_no_number_inputs_that_trackpad_scrolling_can_change(self):
        urls = [reverse("tracker:purchase_new"), reverse("tracker:payment_new"), reverse("tracker:material_add"),
                reverse("tracker:material_edit", args=[self.material.pk]), reverse("tracker:price_history"),
                reverse("tracker:class_basket", args=[self.student.pk])]
        for url in urls:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertNotIn('type="number"', html)
                self.assertIn('inputmode="decimal"', html)

    def test_dashboard_breakdown_includes_every_payment_method(self):
        for method, amount in [("Cash", "10"), ("Card", "20"), ("Bank Transfer", "30"), ("Other", "5")]:
            Payment.objects.create(student=self.student, amount=Decimal(amount), payment_method=method)
        response = self.client.get(reverse("tracker:dashboard"))
        self.assertEqual(response.context["class_totals"]["total"], Decimal("65"))
        self.assertEqual(sum(a for _, a in response.context["class_totals"]["methods"]), Decimal("65"))
        html = response.content.decode()
        for label in ["Cash", "Card", "Bank Transfer", "Other"]:
            self.assertIn(f"{label} <strong>", html)

    def test_opens_without_login_by_default(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("tracker:dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_login_can_be_required(self):
        middleware = [
            "django.contrib.auth.middleware.LoginRequiredMiddleware" if m.endswith("AutoLoginMiddleware") else m
            for m in settings.MIDDLEWARE
        ]
        self.client.logout()
        with self.settings(MIDDLEWARE=middleware, REQUIRE_LOGIN=True):
            response = self.client.get(reverse("tracker:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_pages_render(self):
        for name in ["dashboard", "settings", "student_list", "payments_report", "material_list", "purchase_new", "payment_new"]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"tracker:{name}")).status_code, 200)
        self.assertEqual(self.client.get(self.student.get_absolute_url()).status_code, 200)

    def test_settings_explains_ipad_home_screen_setup(self):
        response = self.client.get(reverse("tracker:settings"))
        self.assertContains(response, "DHCP reservation")
        self.assertContains(response, "Do not use")
        self.assertContains(response, "means the iPad itself")
        self.assertContains(response, reverse("admin:index"))

    def test_settings_shows_current_ipad_address(self):
        with self.settings(STUDIO_LAN_IP="192.168.1.169"):
            response = self.client.get(reverse("tracker:settings"))
        self.assertContains(response, "http://192.168.1.169:8000")

    def test_settings_shows_windows_computer_name_address(self):
        with self.settings(STUDIO_HOSTNAME="LIZ-LAPTOP"):
            response = self.client.get(reverse("tracker:settings"))
        self.assertContains(response, "http://LIZ-LAPTOP:8000")
        self.assertContains(response, "http://LIZ-LAPTOP.local:8000")
        self.assertContains(response, "DHCP reservation")

    def test_saving_backup_folder_copies_database_immediately(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cloud_dir = f"{temp_dir}/OneDrive/Studio Backups"
            def mark_backup_complete(command):
                self.assertEqual(command, "backup_db")
                StudioSettings.objects.filter(pk=1).update(last_backup_date=timezone.localdate())

            with patch("tracker.views.call_command", side_effect=mark_backup_complete) as run_backup:
                response = self.client.post(reverse("tracker:settings"), {"backup_directory": cloud_dir})
            self.assertRedirects(response, reverse("tracker:settings"))
            self.assertEqual(StudioSettings.objects.get(pk=1).backup_directory, cloud_dir)
            self.assertIsNotNone(StudioSettings.objects.get(pk=1).last_backup_date)
            run_backup.assert_called_once_with("backup_db")

    def test_daily_backup_runs_once_after_a_folder_is_configured(self):
        StudioSettings.objects.create(pk=1, backup_directory="/daily-test-backups")

        def mark_backup_complete(command):
            self.assertEqual(command, "backup_db")
            StudioSettings.objects.filter(pk=1).update(last_backup_date=timezone.localdate())

        with patch("tracker.middleware.call_command", side_effect=mark_backup_complete) as run_backup:
            self.client.get(reverse("tracker:dashboard"))
            self.client.get(reverse("tracker:dashboard"))
        run_backup.assert_called_once_with("backup_db")

    def test_failed_daily_backup_is_reported_without_repeating_each_request(self):
        StudioSettings.objects.create(pk=1, backup_directory="/failed-daily-test-backups")
        with patch("tracker.middleware.call_command", side_effect=OSError("OneDrive is unavailable")) as run_backup:
            response = self.client.get(reverse("tracker:dashboard"))
            self.client.get(reverse("tracker:dashboard"))
        run_backup.assert_called_once_with("backup_db")
        self.assertContains(response, "Daily backup failed: OneDrive is unavailable")

    def test_record_purchase_locks_in_price(self):
        response = self.client.post(reverse("tracker:purchase_new"), {
            "student": self.student.pk, "material": self.material.pk, "quantity": "10",
            "purchase_date": "2026-10-31", "notes": "",
        })
        self.assertRedirects(response, reverse("tracker:student_list") + "?class_name=Tue+pm")
        purchase = Purchase.objects.get()
        self.assertEqual(purchase.total_cost, Decimal("1.20"))
        self.assertEqual(purchase.purchase_date, date(2026, 10, 31))

    def test_inactive_material_not_offered(self):
        self.material.is_active = False
        self.material.save()
        response = self.client.post(reverse("tracker:purchase_new"), {
            "student": self.student.pk, "material": self.material.pk, "quantity": "1", "purchase_date": "2026-10-31",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Purchase.objects.exists())

    def test_price_preview_partial(self):
        response = self.client.get(reverse("tracker:price_preview"), {"material": self.material.pk, "quantity": "10"},
                                   headers={"HX-Request": "true"})
        self.assertContains(response, "£1.20")

    def test_date_inputs_use_iso_format(self):
        p = Purchase(student=self.student, material=self.material, quantity=Decimal("1"), purchase_date=date(2026, 2, 4))
        p.set_price(reprice=True)
        p.save()
        response = self.client.get(reverse("tracker:purchase_edit", args=[p.pk]))
        self.assertContains(response, 'value="2026-02-04"')

    def test_next_url_rejects_other_hosts(self):
        response = self.client.post(reverse("tracker:payment_new") + "?next=https://evil.example/", {
            "student": self.student.pk, "amount": "5", "payment_method": "Cash", "payment_date": "2026-10-31",
        })
        self.assertRedirects(response, reverse("tracker:student_list") + "?class_name=Tue+pm")

    def test_students_page_returns_to_the_class_you_were_in(self):
        Student.objects.create(name="Karen", class_name="Tue pm")
        Student.objects.create(name="Wendy", class_name="Wed am")
        all_page = self.client.get(reverse("tracker:student_list"))
        back = "next=/students/%3Fclass_name%3DTue%2Bpm"
        self.assertContains(all_page, back)  # Amy's Purchase button returns to Tue pm, even from "all classes"

        class_page = self.client.get(reverse("tracker:student_list"), {"class_name": "Tue pm"})
        self.assertEqual([g["name"] for g in class_page.context["groups"]], ["Tue pm"])
        self.assertNotContains(class_page, "Wendy")

    def test_payments_report_filters_sales(self):
        shop = Student.objects.create(name="Craft fair", is_sales_channel=True)
        Payment.objects.create(student=self.student, amount=Decimal("5"))
        Payment.objects.create(student=shop, amount=Decimal("40"), payment_method="Card")
        response = self.client.get(reverse("tracker:payments_report"), {"group": "sales"})
        self.assertEqual(response.context["totals"]["total"], Decimal("40"))
        self.assertEqual(response.context["totals"]["card"], Decimal("40"))

    def test_payments_report_defaults_to_this_tax_year(self):
        start, _ = reports.tax_year(timezone.localdate())
        Payment.objects.create(student=self.student, amount=Decimal("5"), payment_date=start)
        Payment.objects.create(student=self.student, amount=Decimal("7"), payment_date=start - timedelta(days=1))
        default = self.client.get(reverse("tracker:payments_report"))
        self.assertEqual(default.context["totals"]["total"], Decimal("5"))
        self.assertContains(default, "Show all payments")
        everything = self.client.get(reverse("tracker:payments_report"), {"all": "1"})
        self.assertEqual(everything.context["totals"]["total"], Decimal("12"))

    def test_balances_and_projects_queries_do_not_grow_with_students(self):
        project = Project.objects.create(name="Ring")

        def add_owing_student(i):
            student = Student.objects.create(name=f"Student {i}", class_name="Tue pm")
            purchase = Purchase(student=student, material=self.material, quantity=Decimal("2"), project=project)
            purchase.set_price(reprice=True)
            purchase.save()

        def count_queries():
            counts = []
            for url in (reverse("tracker:balances"), reverse("tracker:project_list")):
                self.client.get(url)
                with CaptureQueriesContext(connection) as ctx:
                    self.client.get(url)
                counts.append(len(ctx.captured_queries))
            return counts

        add_owing_student(0)
        before = count_queries()
        for i in range(1, 6):
            add_owing_student(i)
        self.assertEqual(count_queries(), before)
        self.assertEqual(len(self.client.get(reverse("tracker:balances")).context["rows"]), 6)

    def test_daily_backup_check_is_skipped_after_the_first_request(self):
        self.client.get(reverse("tracker:dashboard"))
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse("tracker:class_mode"))
        self.assertFalse(any("tracker_studiosettings" in q["sql"] for q in ctx.captured_queries))

    def test_relocate_data_moves_database_out_of_app_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_dir, new_dir = Path(temp_dir) / "app" / "data", Path(temp_dir) / "LocalAppData"
            (old_dir / "backups").mkdir(parents=True)
            (old_dir / "backups" / "studio-1.sqlite3").write_text("x")
            (old_dir / "secret_key.txt").write_text("old-key")
            with sqlite3.connect(old_dir / "studio.sqlite3") as db:
                db.execute("CREATE TABLE t (v TEXT)")
                db.execute("INSERT INTO t VALUES ('live')")
            db.close()
            with self.settings(LEGACY_DATA_DIR=old_dir, DATA_DIR=new_dir):
                call_command("relocate_data", stdout=StringIO())
                out = StringIO()
                call_command("relocate_data", stdout=out)  # second run does nothing
            with sqlite3.connect(new_dir / "studio.sqlite3") as db:
                self.assertEqual(db.execute("SELECT v FROM t").fetchone()[0], "live")
            db.close()
            self.assertEqual((new_dir / "secret_key.txt").read_text(), "old-key")
            self.assertTrue((new_dir / "backups" / "studio-1.sqlite3").exists())
            self.assertFalse((old_dir / "studio.sqlite3").exists())
            self.assertTrue((old_dir / "studio.sqlite3.moved").exists())
            self.assertEqual(out.getvalue(), "")


class BackupSettingsTests(TransactionTestCase):
    def test_saving_backup_folder_writes_a_valid_database_copy(self):
        user = get_user_model().objects.create_user("backup-test")
        self.client.force_login(user)
        with tempfile.TemporaryDirectory() as temp_dir:
            local_dir = Path(temp_dir) / "local"
            cloud_dir = Path(temp_dir) / "OneDrive" / "Studio Backups"
            with self.settings(BACKUP_DIR=local_dir, BACKUP_COPY_DIR=None):
                response = self.client.post(reverse("tracker:settings"), {"backup_directory": str(cloud_dir)})
            self.assertRedirects(response, reverse("tracker:settings"))
            copies = list(cloud_dir.glob("studio-*.sqlite3"))
            self.assertEqual(len(copies), 1)
            with sqlite3.connect(copies[0]) as backup:
                self.assertEqual(backup.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(backup.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            self.assertEqual(StudioSettings.objects.get(pk=1).last_backup_date, timezone.localdate())


class WindowsKeepAwakeTests(TestCase):
    @patch("keep_awake_windows.sys.platform", "win32")
    @patch("keep_awake_windows.subprocess.call", return_value=0)
    @patch("keep_awake_windows.ctypes.WinDLL", create=True)
    def test_prevents_sleep_until_waitress_exits(self, load_kernel32, run_server):
        set_execution_state = Mock(side_effect=[1, 1])
        load_kernel32.return_value.SetThreadExecutionState = set_execution_state

        self.assertEqual(keep_awake_windows.main(), 0)

        self.assertEqual(set_execution_state.call_args_list, [
            call(0x80000001),
            call(0x80000000),
        ])
        run_server.assert_called_once()


@override_settings(SUPPLIER_PRICES_INCLUDE_VAT=True)
class SupplierParsingTests(TestCase):
    def test_cooksongold_fixed_price_adds_vat(self):
        html = '<meta itemprop="price" content="16.280"><meta itemprop="priceCurrency" content="GBP">'
        self.assertEqual(suppliers.parse_cooksongold_price(html, "fixed"), Decimal("19.5360"))

    def test_cooksongold_per_kg_becomes_per_gram(self):
        html = '<meta itemprop="price" content="2097.610 per kg">'
        self.assertEqual(suppliers.parse_cooksongold_price(html, "per_gram"), Decimal("2.5171"))

    @override_settings(SUPPLIER_PRICES_INCLUDE_VAT=False)
    def test_ex_vat_setting(self):
        html = '<meta itemprop="price" content="2097.610 per kg">'
        self.assertEqual(suppliers.parse_cooksongold_price(html, "per_gram_item"), Decimal("2.0976"))

    def test_pricing_type_mismatch_is_reported(self):
        with self.assertRaisesMessage(suppliers.SupplierError, "priced by weight"):
            suppliers.parse_cooksongold_price('<meta itemprop="price" content="2097.610 per kg">', "fixed")

    def test_weight_per_item_survives_split_markup(self):
        html = "<li>Approx. weight of 100 jump rings is 47<span>.8g</span></li>"
        self.assertEqual(suppliers.parse_weight_per_unit(html), Decimal("0.4780"))

    def test_metalclay_json_price(self):
        self.assertEqual(suppliers.parse_metalclay_price({"price": 11995}), Decimal("119.9500"))

    def test_unsupported_and_old_links_explain_themselves(self):
        self.assertIn("only work for", suppliers.fetch_quote("https://example.com/x", "fixed").error)
        collection = suppliers.fetch_quote("https://www.metalclay.co.uk/collections/metal-clay-1", "fixed")
        self.assertIn("collection page", collection.error)

    def test_old_metalclay_link_retries_new_address(self):
        session = Mock()
        session.get.return_value = Mock(status_code=200, ok=True, json=lambda: {"price": 3745})
        quote = suppliers.fetch_quote("https://www.metalclay.co.uk/art-clay-silver-clay-7gm/", "fixed", session)
        self.assertEqual(quote.price, Decimal("37.4500"))
        session.get.assert_called_with("https://www.metalclay.co.uk/products/art-clay-silver-clay-7gm.js", timeout=suppliers.TIMEOUT)


class MaterialManagementTests(TestCase):
    def setUp(self):
        self.findings = Category.objects.create(name="Findings")
        self.material = make_material(category=self.findings, supplier_url="https://www.cooksongold.com/x")

    def test_add_material_reuses_category_case_insensitively(self):
        response = self.client.post(reverse("tracker:material_add"), {
            "name": "Ear hooks", "category_name": "findings", "pricing_type": "fixed", "unit_type": "item",
            "base_price": "6.00", "pack_quantity": "10", "markup_percentage": "50", "is_active": "on",
        })
        self.assertRedirects(response, reverse("tracker:material_list"))
        self.assertEqual(Material.objects.get(name="Ear hooks").category, self.findings)
        self.assertEqual(Category.objects.count(), 1)

    def test_weight_required_for_weight_priced_items(self):
        response = self.client.post(reverse("tracker:material_add"), {
            "name": "Rings", "pricing_type": "per_gram_item", "unit_type": "item", "base_price": "3",
            "pack_quantity": "1", "markup_percentage": "0",
        })
        self.assertContains(response, "Enter the weight of one item")

    def test_manual_price_edit_is_logged(self):
        self.client.post(reverse("tracker:material_edit", args=[self.material.pk]), {
            "name": self.material.name, "category_name": "Findings", "pricing_type": "fixed", "unit_type": "item",
            "base_price": "6.00", "pack_quantity": "50", "markup_percentage": "20", "is_active": "on",
        })
        change = PriceChange.objects.get()
        self.assertEqual((change.old_price, change.new_price, change.source), (Decimal("5.0000"), Decimal("6.0000"), "manual"))

    def test_price_check_then_apply(self):
        quotes = {self.material.pk: suppliers.Quote(price=Decimal("6.0000"))}
        with patch("tracker.views.suppliers.fetch_quotes", return_value=quotes):
            response = self.client.get(reverse("tracker:price_check"))
        self.assertEqual(response.context["n_changed"], 1)
        self.material.refresh_from_db()
        self.assertEqual(self.material.base_price, Decimal("5.0000"))  # nothing saved until confirmed

        self.client.post(reverse("tracker:price_apply"), {"apply": [self.material.pk], f"price_{self.material.pk}": "6.0000"})
        self.material.refresh_from_db()
        self.assertEqual(self.material.base_price, Decimal("6.0000"))
        self.assertEqual(PriceChange.objects.get().old_price, Decimal("5.0000"))

    def test_price_check_shows_supplier_errors(self):
        quotes = {self.material.pk: suppliers.Quote(error="Product page not found")}
        with patch("tracker.views.suppliers.fetch_quotes", return_value=quotes):
            response = self.client.get(reverse("tracker:price_check"))
        self.assertContains(response, "Product page not found")
        self.assertEqual(response.context["n_failed"], 1)

    def test_material_with_purchases_is_not_deleted(self):
        purchase = Purchase(student=Student.objects.create(name="Amy"), material=self.material, quantity=Decimal("1"))
        purchase.set_price(reprice=True)
        purchase.save()
        self.client.post(reverse("tracker:material_delete", args=[self.material.pk]))
        self.assertTrue(Material.objects.filter(pk=self.material.pk).exists())

    def test_toggle_hides_from_purchase_form(self):
        self.client.post(reverse("tracker:material_toggle", args=[self.material.pk]))
        self.material.refresh_from_db()
        self.assertFalse(self.material.is_active)

    def test_reordering(self):
        rings = Category.objects.create(name="Rings", sort_order=5)
        self.client.post(reverse("tracker:category_order"), {"category": [rings.pk, self.findings.pk]})
        self.assertEqual(list(Category.objects.values_list("name", flat=True)), ["Rings", "Findings"])

        Student.objects.create(name="A", class_name="Mon")
        Student.objects.create(name="B", class_name="Tue")
        self.client.post(reverse("tracker:class_reorder"), {"class_name": ["Tue", "Mon"]})
        self.assertEqual(StudioClass.ordered_class_names(), ["Tue", "Mon"])


class SilverPriceTests(TestCase):
    def test_fetches_once_a_day(self):
        with patch("tracker.views.suppliers.fetch_silver_price_per_kg", return_value=Decimal("2097.38")) as fetch:
            self.client.get(reverse("tracker:silver_price"))
            response = self.client.get(reverse("tracker:silver_price"))
        self.assertEqual(fetch.call_count, 1)
        self.assertContains(response, "£2.097")

    def test_shows_last_known_price_when_offline(self):
        SilverPrice.objects.create(price_per_kg=Decimal("2000"), fetched_at=timezone.now() - timedelta(days=2))
        with patch("tracker.views.suppliers.fetch_silver_price_per_kg", side_effect=suppliers.SupplierError("offline")):
            response = self.client.get(reverse("tracker:silver_price"))
        self.assertContains(response, "£2.000")
        self.assertContains(response, "offline")


class ProjectTests(TestCase):
    def test_project_costs_and_delete_keeps_purchases(self):
        project = Project.objects.create(name="Ring")
        material = make_material()
        for name in ["Amy", "Ben"]:
            p = Purchase(student=Student.objects.create(name=name), material=material, quantity=Decimal("10"), project=project)
            p.set_price(reprice=True)
            p.save()
        response = self.client.get(reverse("tracker:project_list"))
        row = response.context["rows"][0]
        self.assertEqual((row["total"], row["average"], len(row["students"])), (Decimal("2.40"), Decimal("1.20"), 2))

        self.client.post(reverse("tracker:project_delete", args=[project.pk]))
        self.assertEqual(Purchase.objects.filter(project__isnull=True).count(), 2)


class ImportTests(TestCase):
    def test_if_empty_skips_when_data_exists(self):
        Student.objects.create(name="Already here")
        out = StringIO()
        with tempfile.NamedTemporaryFile(suffix=".db") as legacy:
            call_command("import_legacy", legacy.name, "--if-empty", stdout=out)
        self.assertIn("not importing", out.getvalue())

    def test_penny_rounding_keeps_each_students_total(self):
        from tracker.management.commands.import_legacy import penny_totals
        rows = [{"id": 1, "student_id": 1, "total_cost": 1.425}, {"id": 2, "student_id": 1, "total_cost": 1.425},
                {"id": 3, "student_id": 1, "total_cost": 1.425}, {"id": 4, "student_id": 2, "total_cost": 0.962}]
        totals = penny_totals(rows)
        self.assertEqual(sum(totals[i] for i in (1, 2, 3)), Decimal("4.28"))  # rounding each would give 4.29
        self.assertTrue(all(abs(totals[i] - Decimal("1.425")) < Decimal("0.01") for i in (1, 2, 3)))
        self.assertEqual(totals[4], Decimal("0.96"))

    def test_purchases_of_deleted_materials_are_kept(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as legacy, tempfile.NamedTemporaryFile(suffix=".db") as older:
            db = sqlite3.connect(older.name)
            db.executescript(LEGACY_SCHEMA + """
                INSERT INTO materials VALUES (7, 'D wire', 'wire', 'gram', 3.3239, 1, 20, 'Cooksongold', '', 1, 'per_kg', NULL, '');
            """)
            db.commit()
            db.close()
            db = sqlite3.connect(legacy.name)
            db.executescript(LEGACY_SCHEMA + """
                INSERT INTO students VALUES (1, 'Amy', 'Tue', '', '', '', 0, '2026-01-06 10:00:00');
                INSERT INTO purchases VALUES (1, 1, NULL, 7, 2.5, 3.99, 9.975, '2026-01-07', '');
                INSERT INTO purchases VALUES (2, 1, NULL, 60, 1.5, 3.465, 5.1975, '2026-03-07', '');
            """)
            db.commit()
            db.close()
            out = StringIO()
            call_command("import_legacy", legacy.name, "--recover-from", older.name, stdout=out)
        recovered, unknown = Material.objects.get(pk=7), Material.objects.get(pk=60)
        self.assertEqual((recovered.name, recovered.is_active, recovered.markup_percentage), ("D wire", False, Decimal("20.00")))
        self.assertEqual((unknown.name, unknown.unit_type, unknown.pricing_type, unknown.base_price, unknown.is_active),
                         ("Deleted material #60", "gram", "per_gram", Decimal("3.4650"), False))
        self.assertEqual(Purchase.objects.count(), 2)
        self.assertIn("Verified balances", out.getvalue())
        self.assertIn("Recreated deleted material #60", out.getvalue())


class ClassModeTests(TestCase):
    def setUp(self):
        self.anne = Student.objects.create(name="Anne", class_name="Tue pm")
        self.rings = make_material(name="Jump rings 10mm")  # £5 / 50 + 20% = £0.12 each
        self.sheet = make_material(name="Silver sheet", pricing_type=Material.PricingType.PER_GRAM, unit_type="gram",
                                   base_price=Decimal("2.50"), pack_quantity=Decimal("1"), markup_percentage=Decimal("20"))
        self.basket_url = reverse("tracker:class_basket", args=[self.anne.pk])

    def test_pages_render(self):
        self.assertContains(self.client.get(reverse("tracker:class_mode")), "Tue pm")
        self.assertContains(self.client.get(reverse("tracker:class_mode"), {"class_name": "Tue pm"}), "Anne")
        self.assertEqual(self.client.get(self.basket_url).status_code, 200)

    def test_mode_switch_in_header(self):
        self.assertContains(self.client.get(reverse("tracker:dashboard")), "Switch to class mode")
        for url in [reverse("tracker:class_mode"), self.basket_url]:
            page = self.client.get(url)
            self.assertContains(page, "Switch to Liz mode")
            self.assertNotContains(page, "Switch to class mode")

    def test_basket_saves_every_line_and_returns_to_class(self):
        response = self.client.post(self.basket_url, {
            f"qty_{self.rings.pk}": "10", f"qty_{self.sheet.pk}": "2.5", "qty_999": "3", "purchase_date": "2026-10-31",
        })
        self.assertRedirects(response, reverse("tracker:class_mode") + "?class_name=Tue+pm")
        totals = sorted(Purchase.objects.values_list("total_cost", flat=True))
        self.assertEqual(totals, [Decimal("1.20"), Decimal("7.50")])

    def test_basket_ignores_blank_zero_and_hidden_materials(self):
        self.sheet.is_active = False
        self.sheet.save()
        self.client.post(self.basket_url, {f"qty_{self.rings.pk}": "0", f"qty_{self.sheet.pk}": "2", "qty_x": "1"})
        self.assertFalse(Purchase.objects.exists())

    def test_class_screens_hide_costs_and_admin_menu(self):
        Student.objects.create(name="Karen", class_name="Tue pm")
        Payment.objects.create(student=self.anne, amount=Decimal("1"))
        for url in [self.basket_url, reverse("tracker:class_mode") + "?class_name=Tue+pm",
                    reverse("tracker:class_search") + "?q=sheet"]:
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                for secret in ["markup", "Markup", "£5.00", "£2.50", "Supplier", 'href="/payments/"', 'href="/materials/"',
                               'href="/reports/"', "Reports", "Profit"]:
                    self.assertNotIn(secret, html)
        self.assertContains(self.client.get(self.basket_url), "£3.00")  # student price per gram

    def test_search_matches_all_words(self):
        response = self.client.get(reverse("tracker:class_search"), {"q": "jump 10"})
        self.assertEqual(list(response.context["materials"]), [self.rings])

    def test_quick_buttons_prefer_favourites(self):
        response = self.client.get(self.basket_url)
        self.assertEqual(len(response.context["quick"]), 2)
        self.sheet.is_favourite = True
        self.sheet.save()
        response = self.client.get(self.basket_url)
        self.assertEqual(list(response.context["quick"]), [self.sheet])

    def test_settle_up_pays_exact_amount_and_can_be_undone(self):
        self.client.post(self.basket_url, {f"qty_{self.sheet.pk}": "2.5"})
        self.client.post(reverse("tracker:settle_up", args=[self.anne.pk]), {"method": "Card"})
        payment = Payment.objects.get()
        self.assertEqual((payment.amount, payment.payment_method), (Decimal("7.50"), "Card"))

        undo_id = self.client.session["undo"]["id"]
        self.client.post(reverse("tracker:undo"), {"id": undo_id})
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(Purchase.objects.count(), 1)

    def test_settle_up_when_nothing_owed(self):
        self.client.post(reverse("tracker:settle_up", args=[self.anne.pk]), {"method": "Cash"})
        self.assertFalse(Payment.objects.exists())

    def test_undo_basket_removes_what_was_added(self):
        self.client.post(self.basket_url, {f"qty_{self.rings.pk}": "10", f"qty_{self.sheet.pk}": "1"})
        response = self.client.get(reverse("tracker:class_mode"), {"class_name": "Tue pm"})
        self.assertContains(response, "Added 2 items (£4.20) for Anne.")
        self.client.post(reverse("tracker:undo"), {"id": self.client.session["undo"]["id"]})
        self.assertFalse(Purchase.objects.exists())


class UndoDeleteTests(TestCase):
    def test_deleted_purchase_and_payment_come_back(self):
        student = Student.objects.create(name="Amy")
        purchase = Purchase(student=student, material=make_material(), quantity=Decimal("3"), notes="ring")
        purchase.set_price(reprice=True)
        purchase.save()
        self.client.post(reverse("tracker:purchase_delete", args=[purchase.pk]))
        self.assertFalse(Purchase.objects.exists())
        self.client.post(reverse("tracker:undo"), {"id": self.client.session["undo"]["id"]})
        restored = Purchase.objects.get()
        self.assertEqual((restored.pk, restored.notes, restored.total_cost), (purchase.pk, "ring", Decimal("0.36")))

        payment = Payment.objects.create(student=student, amount=Decimal("2"))
        self.client.post(reverse("tracker:payment_delete", args=[payment.pk]))
        self.client.post(reverse("tracker:undo"), {"id": self.client.session["undo"]["id"]})
        self.assertTrue(Payment.objects.filter(pk=payment.pk).exists())

    def test_undo_bar_shows_once_and_rejects_stale_ids(self):
        payment = Payment.objects.create(student=Student.objects.create(name="Amy"), amount=Decimal("2"))
        self.client.post(reverse("tracker:payment_delete", args=[payment.pk]))
        self.assertContains(self.client.get(reverse("tracker:dashboard")), "Undo</button>")
        self.assertNotContains(self.client.get(reverse("tracker:dashboard")), "Undo</button>")
        self.client.post(reverse("tracker:undo"), {"id": "wrong"})
        self.assertFalse(Payment.objects.exists())

    def test_purchase_preview_hides_supplier_cost(self):
        material = make_material()
        response = self.client.get(reverse("tracker:price_preview"), {"material": material.pk, "quantity": "10"})
        self.assertNotContains(response, "Pack of")
        self.assertNotContains(response, "£5.00")


class CostAndProfitTests(TestCase):
    def setUp(self):
        self.material = make_material()  # cost £0.10 each, sells at £0.12

    def buy(self, student, qty, when):
        p = Purchase(student=student, material=self.material, quantity=Decimal(qty), purchase_date=when)
        p.set_price(reprice=True)
        p.save()
        return p

    def test_cost_is_frozen_at_time_of_sale(self):
        p = self.buy(Student.objects.create(name="Amy"), "10", date(2026, 10, 1))
        self.assertEqual((p.unit_cost, p.cost_total, p.cost_is_estimate), (Decimal("0.1000"), Decimal("1.00"), False))
        self.material.base_price = Decimal("10.00")
        self.material.save()
        p.quantity = Decimal("20")
        p.set_price(reprice=False)
        self.assertEqual((p.unit_cost, p.cost_total, p.total_cost), (Decimal("0.1000"), Decimal("2.00"), Decimal("2.40")))

    def test_estimated_cost_takes_markup_back_off(self):
        self.assertEqual(estimated_unit_cost(Decimal("0.1200"), Decimal("20")), Decimal("0.1000"))
        self.assertEqual(estimated_unit_cost(Decimal("1.5200"), Decimal("0")), Decimal("1.5200"))

    def test_profit_report_totals_and_groupings(self):
        self.buy(Student.objects.create(name="Amy", class_name="Tue"), "10", date(2026, 9, 5))
        self.buy(Student.objects.create(name="Ben", class_name="Wed"), "50", date(2026, 10, 7))
        response = self.client.get(reverse("tracker:reports"))
        total = response.context["total"]
        self.assertEqual((total["sales"], total["cost"], total["profit"]), (Decimal("7.20"), Decimal("6.00"), Decimal("1.20")))
        self.assertEqual([r["label"] for r in response.context["by_class"]], ["Wed", "Tue"])
        self.assertEqual(len(response.context["by_month"]), 2)

        october = self.client.get(reverse("tracker:reports"), {"start": "2026-10-01"}).context["total"]
        self.assertEqual(october["profit"], Decimal("1.00"))

    def test_old_profit_link_redirects(self):
        response = self.client.get("/profit/?start=2026-10-01")
        self.assertRedirects(response, reverse("tracker:reports") + "?start=2026-10-01")

    def test_import_marks_legacy_costs_as_estimates(self):
        Material.objects.all().delete()  # import only runs into an empty database
        with tempfile.NamedTemporaryFile(suffix=".db") as legacy:
            db = sqlite3.connect(legacy.name)
            db.executescript(LEGACY_SCHEMA + """
                INSERT INTO students VALUES (1, 'Amy', 'Tue', '', '', '', 0, '2026-01-06 10:00:00');
                INSERT INTO materials VALUES (1, 'Sheet', 'sheet silver', 'gram', 3.1891, 1, 20, 'Cooksongold', '', 1, 'per_kg', NULL, '');
                INSERT INTO purchases VALUES (1, 1, NULL, 1, 2, 3.82692, 7.65384, '2026-01-07', '');
                INSERT INTO payments VALUES (1, 1, 5, '2026-01-07', 'Cash', '');
            """)
            db.commit()
            db.close()
            call_command("import_legacy", legacy.name, stdout=StringIO())
        p = Purchase.objects.get()
        self.assertEqual((p.unit_cost, p.cost_total, p.cost_is_estimate), (Decimal("3.1891"), Decimal("6.38"), True))
        self.assertEqual(Material.objects.get().pricing_type, "per_gram")


class StatementTests(TestCase):
    def setUp(self):
        self.amy = Student.objects.create(name="Amy Smith", class_name="Tue", email="amy@example.com")
        self.rings = make_material(name="Jump rings")  # £0.12 each
        self.sheet = make_material(name="Silver sheet", unit_type="gram", base_price=Decimal("3.00"),
                                   pack_quantity=Decimal("1"), markup_percentage=Decimal("0"))

    def buy(self, material, qty, when):
        p = Purchase(student=self.amy, material=material, quantity=Decimal(qty), purchase_date=when)
        p.set_price(reprice=True)
        p.save()

    def test_payments_clear_oldest_purchases_first(self):
        self.buy(self.rings, "10", date(2026, 9, 1))   # £1.20
        self.buy(self.sheet, "2.5", date(2026, 10, 1))  # £7.50
        self.buy(self.rings, "5", date(2026, 10, 8))    # £0.60
        Payment.objects.create(student=self.amy, amount=Decimal("1.20"))
        st = statements.statement_for(self.amy)
        self.assertEqual(st.owed, Decimal("8.10"))
        self.assertEqual([i["label"] for i in st.items], ["Silver sheet, 2.5g", "Jump rings × 5"])

    def test_email_is_a_summary_without_rates(self):
        self.buy(self.rings, "10", date(2026, 9, 1))
        st = statements.statement_for(self.amy)
        body = st.email_body()
        self.assertIn("Hi Amy,", body)
        self.assertIn("£1.20", body)
        self.assertIn("Jump rings × 10", body)
        self.assertNotIn("£0.12", body)
        self.assertTrue(st.mailto().startswith("mailto:amy@example.com?subject=Your%20materials%20balance"))

    def test_no_email_button_without_address_or_debt(self):
        self.assertEqual(statements.statement_for(self.amy).owed, Decimal("0"))
        self.amy.email = ""
        self.amy.save()
        self.buy(self.rings, "1", date(2026, 9, 1))
        self.assertEqual(statements.statement_for(self.amy).mailto(), "")

    def test_credit_is_reported(self):
        Payment.objects.create(student=self.amy, amount=Decimal("5"))
        st = statements.statement_for(self.amy)
        self.assertEqual((st.owed, st.credit, st.items), (Decimal("0"), Decimal("5"), []))

    def test_statement_and_balances_pages(self):
        self.buy(self.sheet, "2", date(2026, 10, 1))
        Student.objects.create(name="Paid up")
        statement = self.client.get(reverse("tracker:student_statement", args=[self.amy.pk]))
        self.assertContains(statement, "Balance due")
        self.assertContains(statement, "£6.00")
        for secret in ["markup", "Markup", "cost", "Supplier"]:
            self.assertNotContains(statement, secret)

        balances = self.client.get(reverse("tracker:balances"))
        self.assertEqual([st.student.name for st in balances.context["rows"]], ["Amy Smith"])
        self.assertContains(balances, "mailto:amy@example.com")


class ClassesAndArchiveTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.autumn = StudioClass.objects.create(name="Autumn", start_date=today - timedelta(days=60),
                                                 end_date=today - timedelta(days=1))
        self.winter = StudioClass.objects.create(name="Winter", start_date=today + timedelta(days=7))
        self.ongoing = StudioClass.objects.create(name="Tuesday drop-in")
        self.old = Student.objects.create(name="Olive", class_name="Autumn")
        self.new = Student.objects.create(name="Nina", class_name="Winter")
        self.drop = Student.objects.create(name="Dee", class_name="Tuesday drop-in")
        self.loose = Student.objects.create(name="Lou")
        self.shop = Student.objects.create(name="Market", is_sales_channel=True)

    def test_status_from_dates(self):
        self.assertEqual([self.autumn.status, self.winter.status, self.ongoing.status], ["finished", "upcoming", "current"])

    def test_sales_channels_dont_become_classes(self):
        Student.objects.create(name="Craft fair", class_name="Fairs", is_sales_channel=True)
        self.assertFalse(StudioClass.objects.filter(name="Fairs").exists())

    def test_archive_is_previewed_not_automatic(self):
        response = self.client.get(reverse("tracker:archive_students"))
        self.assertEqual({s.name for s in response.context["candidates"]}, {"Olive", "Lou"})
        self.assertFalse(Student.objects.filter(is_archived=True).exists())

    def test_archive_only_ticked_students_and_undo(self):
        self.client.post(reverse("tracker:archive_students"), {"student": [self.old.pk, self.new.pk]})
        self.assertEqual(set(Student.objects.filter(is_archived=True).values_list("name", flat=True)), {"Olive"})
        self.client.post(reverse("tracker:undo"), {"id": self.client.session["undo"]["id"]})
        self.assertFalse(Student.objects.filter(is_archived=True).exists())

    def test_archived_hidden_from_everyday_lists_but_not_from_money(self):
        material = make_material()
        p = Purchase(student=self.old, material=material, quantity=Decimal("10"))
        p.set_price(reprice=True)
        p.save()
        self.client.post(reverse("tracker:student_archive", args=[self.old.pk]))

        names = [s.name for g in self.client.get(reverse("tracker:student_list")).context["groups"] for s in g["students"]]
        self.assertNotIn("Olive", names)
        self.assertNotContains(self.client.get(reverse("tracker:class_mode"), {"class_name": "Autumn"}), "Olive")
        purchase_students = self.client.get(reverse("tracker:purchase_new")).context["form"].fields["student"].queryset
        self.assertNotIn(self.old, purchase_students)

        payment_students = list(self.client.get(reverse("tracker:payment_new")).context["form"].fields["student"].queryset)
        self.assertEqual(payment_students[-1], self.old)  # still payable, listed last
        self.assertEqual([st.student for st in self.client.get(reverse("tracker:balances")).context["rows"]], [self.old])
        self.assertContains(self.client.get(reverse("tracker:archived_students"), {"q": "oli"}), "Olive")

    def test_adding_student_to_class_lists_archived_last_and_restores_them(self):
        self.old.is_archived = True
        self.old.save()
        candidates = list(self.client.get(reverse("tracker:class_detail", args=[self.winter.pk])).context["candidates"])
        self.assertEqual([s.name for s in candidates], ["Dee", "Lou", "Olive"])
        found = self.client.get(reverse("tracker:class_add_search", args=[self.winter.pk]), {"q": "oli"})
        self.assertEqual(list(found.context["candidates"]), [self.old])

        self.client.post(reverse("tracker:class_add_student", args=[self.winter.pk, self.old.pk]))
        self.old.refresh_from_db()
        self.assertEqual((self.old.class_name, self.old.is_archived), ("Winter", False))

    def test_purchases_keep_their_class_when_student_moves(self):
        material = make_material()
        p = Purchase(student=self.old, material=material, quantity=Decimal("10"))
        p.set_price(reprice=True)
        p.save()
        self.client.post(reverse("tracker:class_add_student", args=[self.winter.pk, self.old.pk]))
        p.refresh_from_db()
        self.assertEqual(p.class_name, "Autumn")
        labels = [r["label"] for r in self.client.get(reverse("tracker:reports")).context["by_class"]]
        self.assertEqual(labels, ["Autumn"])

    def test_renaming_class_updates_students_and_purchases(self):
        p = Purchase(student=self.drop, material=make_material(), quantity=Decimal("1"))
        p.set_price(reprice=True)
        p.save()
        self.client.post(reverse("tracker:class_edit", args=[self.ongoing.pk]), {"name": "Tuesday evenings"})
        self.drop.refresh_from_db()
        p.refresh_from_db()
        self.assertEqual((self.drop.class_name, p.class_name), ("Tuesday evenings", "Tuesday evenings"))

    def test_classes_page_and_dashboard_hide_finished_classes(self):
        response = self.client.get(reverse("tracker:class_list"))
        self.assertEqual(response.context["n_candidates"], 2)
        dashboard_classes = [name for name, _ in self.client.get(reverse("tracker:dashboard")).context["classes"]]
        self.assertNotIn("Autumn", dashboard_classes)
        self.assertIn("Winter", dashboard_classes)


class ReportsTests(TestCase):
    def setUp(self):
        self.amy = Student.objects.create(name="Amy", class_name="Tue")
        material = make_material()  # cost £0.10, sells at £0.12
        for qty, when in [("10", date(2026, 4, 5)), ("50", date(2026, 4, 20))]:
            p = Purchase(student=self.amy, material=material, quantity=Decimal(qty), purchase_date=when)
            p.set_price(reprice=True)
            p.save()
        Payment.objects.create(student=self.amy, amount=Decimal("10"), payment_method="Cash", payment_date=date(2026, 4, 2))
        Payment.objects.create(student=self.amy, amount=Decimal("4"), payment_method="Card", payment_date=date(2026, 4, 21))
        Payment.objects.create(student=self.amy, amount=Decimal("1"), payment_method="Bank Transfer",
                               payment_date=date(2026, 4, 22), notes="=HYPERLINK(\"x\")")

    def test_uk_tax_year(self):
        self.assertEqual(reports.tax_year(date(2026, 4, 5)), (date(2025, 4, 6), date(2026, 4, 5)))
        self.assertEqual(reports.tax_year(date(2026, 4, 6)), (date(2026, 4, 6), date(2027, 4, 5)))
        labels = [p[0] for p in reports.presets(date(2026, 1, 10))]
        self.assertEqual(labels, ["Tax year 2025/26", "Tax year 2024/25", "2026", "All time"])

    def test_monthly_income_split_by_method(self):
        april = self.client.get(reverse("tracker:reports")).context["by_month"][0]
        self.assertEqual((april["cash"], april["card"], april["other"], april["income"]),
                         (Decimal("10"), Decimal("4"), Decimal("1"), Decimal("15")))
        self.assertEqual((april["sales"], april["cost"], april["profit"]), (Decimal("7.20"), Decimal("6.00"), Decimal("1.20")))

    def test_date_range_applies_to_income_and_sales(self):
        context = self.client.get(reverse("tracker:reports"), {"start": "2026-04-06", "end": "2027-04-05"}).context
        self.assertEqual(context["income"]["total"], Decimal("5"))
        self.assertEqual(context["total"]["sales"], Decimal("6.00"))

    def test_csv_downloads(self):
        monthly = self.client.get(reverse("tracker:reports_csv", args=["monthly"]))
        self.assertEqual(monthly["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn("attachment;", monthly["Content-Disposition"])
        lines = monthly.content.decode("utf-8-sig").splitlines()
        self.assertEqual(lines[0].split(",")[0], "Month")
        self.assertEqual(lines[1], "2026-04,10.00,4.00,1.00,15.00,7.20,6.00,1.20,0.00,0.00")

        payments = self.client.get(reverse("tracker:reports_csv", args=["payments"]), {"start": "2026-04-20"})
        rows = payments.content.decode("utf-8-sig").splitlines()
        self.assertEqual(len(rows), 3)
        self.assertIn("'=HYPERLINK", rows[2])  # formulas are neutralised

        sales = self.client.get(reverse("tracker:reports_csv", args=["sales"]))
        rows = sales.content.decode("utf-8-sig").splitlines()
        self.assertEqual(rows[1].split(",")[:5], ["2026-04-05", "Amy", "Tue", "Material", "Jump rings"])


class PriceHistoryAndMarginTests(TestCase):
    def test_low_markup_is_flagged(self):
        thin = make_material(name="Wire", markup_percentage=Decimal("10"))
        fine = make_material(name="Sheet", markup_percentage=Decimal("50"))
        flags = margins.flag_materials([thin, fine])
        self.assertIn(thin.pk, flags)
        self.assertNotIn(fine.pk, flags)
        self.assertContains(self.client.get(reverse("tracker:material_list")), "Thin margin")

    def test_silver_rise_since_price_was_set_is_flagged(self):
        now = timezone.now()
        silver_sheet = make_material(name="Silver sheet", pricing_type="per_gram", base_price=Decimal("1.00"),
                                     pack_quantity=Decimal("1"), markup_percentage=Decimal("20"),
                                     price_date=timezone.localdate() - timedelta(days=29))
        SilverPrice.objects.create(price_per_kg=Decimal("1000"), fetched_at=now - timedelta(days=30))
        self.assertEqual(margins.flag_materials([silver_sheet]), {})  # 20% markup = 16.7% margin, silver unchanged

        SilverPrice.objects.create(price_per_kg=Decimal("1100"), fetched_at=now - timedelta(days=1))
        flags = margins.flag_materials([silver_sheet])
        self.assertIn("Silver is up 10%", flags[silver_sheet.pk][0])  # real margin now (1.20 - 1.10) / 1.20 = 8%

        silver_sheet.price_date = timezone.localdate()
        self.assertEqual(margins.flag_materials([silver_sheet]), {})  # re-priced after the rise

    def test_price_history_page(self):
        material = make_material()
        PriceChange.objects.create(material=material, old_price=Decimal("4.00"), new_price=Decimal("5.00"))
        SilverPrice.objects.create(price_per_kg=Decimal("1000"), fetched_at=timezone.now() - timedelta(days=1))
        SilverPrice.objects.create(price_per_kg=Decimal("1100"))
        response = self.client.get(reverse("tracker:price_history"))
        self.assertContains(response, "+25.0%")
        self.assertContains(response, "+10.0%")
        only = self.client.get(reverse("tracker:price_history"), {"material": material.pk})
        self.assertEqual(only.context["material"], material)
        self.assertEqual(only.context["silver"], [])
        self.assertEqual(self.client.get(reverse("tracker:price_history"), {"material": "x"}).status_code, 200)


def at_noon(day):
    return timezone.make_aware(datetime.combine(day, datetime.min.time().replace(hour=12)))


class SilverCostTests(TestCase):
    def setUp(self):
        self.priced_on = date(2026, 3, 1)
        self.sheet = make_material(name="Sterling sheet", pricing_type="per_gram", unit_type="gram",
                                   base_price=Decimal("1.00"), pack_quantity=Decimal("1"),
                                   markup_percentage=Decimal("20"), is_silver=True, price_date=self.priced_on)
        self.rings = make_material()  # not silver
        SilverPrice.objects.create(price_per_kg=Decimal("1000"), fetched_at=at_noon(self.priced_on))
        SilverPrice.objects.create(price_per_kg=Decimal("1100"), fetched_at=at_noon(date(2026, 3, 10)))
        self.amy = Student.objects.create(name="Amy", class_name="Tue")

    def buy(self, material, qty, when):
        p = Purchase(student=self.amy, material=material, quantity=Decimal(qty), purchase_date=when)
        p.set_price(reprice=True)
        p.save()
        return p

    def test_silver_cost_uses_silver_price_on_day_of_sale(self):
        on_price_day = self.buy(self.sheet, "10", self.priced_on)
        later = self.buy(self.sheet, "10", date(2026, 3, 12))  # no reading that day: uses 10 March
        self.assertEqual((on_price_day.unit_cost, on_price_day.cost_total, on_price_day.silver_rate),
                         (Decimal("1.0000"), Decimal("10.00"), Decimal("1000.00")))
        self.assertEqual((later.unit_cost, later.cost_total, later.silver_rate),
                         (Decimal("1.1000"), Decimal("11.00"), Decimal("1100.00")))
        self.assertEqual(later.total_cost, Decimal("12.00"))  # students still pay the price at the time

    def test_sale_before_first_reading_keeps_cost_until_a_past_price_is_added(self):
        early = self.buy(self.sheet, "10", date(2026, 1, 15))
        self.assertEqual((early.unit_cost, early.silver_rate), (Decimal("1.0000"), None))

        response = self.client.post(reverse("tracker:silver_add"), {"day": "2026-01-14", "price_per_kg": "900"})
        self.assertRedirects(response, reverse("tracker:price_history"))
        early.refresh_from_db()
        self.assertEqual((early.unit_cost, early.cost_total, early.silver_rate),
                         (Decimal("0.9000"), Decimal("9.00"), Decimal("900.00")))
        self.assertEqual(SilverPrice.objects.get(price_per_kg=900).source, "manual")

        reading = SilverPrice.objects.get(price_per_kg=900)
        self.client.post(reverse("tracker:silver_delete", args=[reading.pk]))
        self.assertFalse(SilverPrice.objects.filter(pk=reading.pk).exists())

    def test_future_silver_price_rejected(self):
        self.client.post(reverse("tracker:silver_add"),
                         {"day": (timezone.localdate() + timedelta(days=1)).isoformat(), "price_per_kg": "900"})
        self.assertFalse(SilverPrice.objects.filter(price_per_kg=900).exists())

    def test_new_silver_reading_recosts_sales(self):
        sale = self.buy(self.sheet, "10", date(2026, 3, 20))
        self.buy(self.sheet, "10", date(2026, 3, 12))
        self.assertEqual(sale.unit_cost, Decimal("1.1000"))
        reading = SilverPrice.objects.create(price_per_kg=Decimal("1200"), fetched_at=at_noon(date(2026, 3, 20)))
        sale.refresh_from_db()
        self.assertEqual((sale.unit_cost, sale.silver_rate), (Decimal("1.2000"), Decimal("1200.00")))
        self.assertEqual(silver.recost(), 0)  # already up to date

        with patch("tracker.silver.apply", wraps=silver.apply) as applied:
            silver.recost(since=date(2026, 3, 20))
        self.assertEqual([c.args[0].pk for c in applied.call_args_list], [sale.pk])  # 12 March sale untouched

        reading.delete()
        sale.refresh_from_db()
        self.assertEqual(sale.unit_cost, Decimal("1.1000"))

    def test_undoing_a_silver_price_recosts_sales(self):
        sale = self.buy(self.sheet, "10", date(2026, 3, 20))
        self.client.post(reverse("tracker:silver_add"), {"day": "2026-03-20", "price_per_kg": "1200"})
        sale.refresh_from_db()
        self.assertEqual(sale.unit_cost, Decimal("1.2000"))
        undo_id = self.client.session["undo"]["id"]
        self.client.post(reverse("tracker:undo"), {"id": undo_id})
        sale.refresh_from_db()
        self.assertEqual(sale.unit_cost, Decimal("1.1000"))

    def test_saving_one_silver_sale_does_not_load_every_reading(self):
        with CaptureQueriesContext(connection) as queries:
            self.buy(self.sheet, "10", date(2026, 3, 12))
        reading_queries = [q["sql"] for q in queries.captured_queries if "tracker_silverprice" in q["sql"]]
        self.assertEqual(len(reading_queries), 2)
        self.assertTrue(all("LIMIT 1" in sql for sql in reading_queries))

    def test_non_silver_cost_is_unchanged(self):
        p = self.buy(self.rings, "10", date(2026, 3, 12))
        self.assertEqual((p.unit_cost, p.silver_rate), (Decimal("0.1000"), None))

    def test_reports_by_class_silver_only(self):
        self.buy(self.sheet, "10", date(2026, 3, 12))  # sales 12.00, cost 11.00
        self.buy(self.rings, "10", date(2026, 3, 12))  # sales 1.20, cost 1.00
        all_rows = self.client.get(reverse("tracker:reports")).context["by_class"]
        self.assertEqual(all_rows[0]["sales"], Decimal("13.20"))
        response = self.client.get(reverse("tracker:reports"), {"by_class": "silver"})
        self.assertEqual(response.context["by_class"][0]["sales"], Decimal("12.00"))
        self.assertEqual(response.context["by_class"][0]["profit"], Decimal("1.00"))
        self.assertEqual(response.context["total"]["sales"], Decimal("13.20"))  # only the class table is filtered
        self.assertContains(response, "Silver only")

    def test_editing_price_moves_price_date_and_recosts(self):
        sale = self.buy(self.sheet, "10", date(2026, 3, 12))
        SilverPrice.objects.create(price_per_kg=Decimal("1100"), fetched_at=timezone.now())
        data = {"name": self.sheet.name, "category_name": "", "pricing_type": "per_gram", "unit_type": "gram",
                "base_price": "1.32", "pack_quantity": "1", "markup_percentage": "20", "supplier": "",
                "supplier_url": "", "is_active": "on", "is_silver": "on", "price_date": "2026-03-01", "notes": ""}
        response = self.client.post(reverse("tracker:material_edit", args=[self.sheet.pk]), data)
        self.assertRedirects(response, reverse("tracker:material_list"))
        self.sheet.refresh_from_db()
        self.assertEqual(self.sheet.price_date, timezone.localdate())
        sale.refresh_from_db()
        self.assertEqual(sale.unit_cost, Decimal("1.3200"))  # £1.32 today at £1100/kg = £1.32 on 12 March at £1100/kg


class ClassPaymentTests(TestCase):
    def setUp(self):
        self.anne = Student.objects.create(name="Anne", class_name="Tue pm")
        self.url = reverse("tracker:class_payment", args=[self.anne.pk])

    def test_basket_page_has_payment_form(self):
        response = self.client.get(reverse("tracker:class_basket", args=[self.anne.pk]))
        self.assertContains(response, "Record a payment")
        self.assertContains(response, 'value="Bank Transfer"')

    def test_record_payment_returns_to_class(self):
        response = self.client.post(self.url, {"amount": "12.50", "payment_method": "Card", "payment_date": "",
                                               "notes": "Deposit"})
        self.assertRedirects(response, reverse("tracker:class_mode") + "?class_name=Tue+pm")
        payment = Payment.objects.get()
        self.assertEqual((payment.student, payment.amount, payment.payment_method, payment.payment_date, payment.notes),
                         (self.anne, Decimal("12.50"), "Card", timezone.localdate(), "Deposit"))

    def test_invalid_payment_is_not_saved(self):
        other = Student.objects.create(name="Karen")
        response = self.client.post(self.url, {"amount": "0", "payment_method": "Cash", "student": other.pk})
        self.assertRedirects(response, reverse("tracker:class_basket", args=[self.anne.pk]))
        self.assertFalse(Payment.objects.exists())
        self.client.post(self.url, {"amount": "5", "payment_method": "Cash", "student": other.pk})
        self.assertEqual(Payment.objects.get().student, self.anne)


class MaterialKindTests(TestCase):
    def setUp(self):
        self.amy = Student.objects.create(name="Amy", class_name="Tue")
        self.rings = make_material()  # sells at £0.12 each, costs £0.10
        self.lesson = make_material(name="Lesson – pay as you go", kind="lesson", base_price=Decimal("27.50"),
                                    pack_quantity=Decimal("1"), markup_percentage=Decimal("0"))
        self.order = make_material(name="Cookson order", kind="order", base_price=Decimal("1"),
                                   pack_quantity=Decimal("1"), markup_percentage=Decimal("0"))

    def buy(self, material, qty):
        p = Purchase(student=self.amy, material=material, quantity=Decimal(qty), purchase_date=date(2026, 5, 1))
        p.set_price(reprice=True)
        p.save()
        return p

    def test_reports_keep_lessons_and_orders_out_of_materials_profit(self):
        self.buy(self.rings, "10")
        self.buy(self.lesson, "2")
        self.buy(self.order, "12.50")
        context = self.client.get(reverse("tracker:reports")).context
        self.assertEqual((context["total"]["sales"], context["total"]["profit"]), (Decimal("1.20"), Decimal("0.20")))
        self.assertEqual((context["lesson_fees"], context["orders_at_cost"]), (Decimal("55.00"), Decimal("12.50")))
        month = context["by_month"][0]
        self.assertEqual((month["sales"], month["lessons"], month["orders"]),
                         (Decimal("1.20"), Decimal("55.00"), Decimal("12.50")))
        self.assertEqual([r["label"] for r in context["by_material"]], ["Jump rings"])
        self.assertEqual(context["by_class"][0]["sales"], Decimal("1.20"))

    def test_lessons_and_orders_are_not_margin_flagged(self):
        self.assertEqual(margins.flag_materials([self.lesson, self.order]), {})

    def test_order_form_needs_no_price(self):
        data = {"name": "Metal clay order", "kind": "order", "category_name": "", "pricing_type": "per_gram",
                "unit_type": "item", "base_price": "", "pack_quantity": "", "markup_percentage": "",
                "supplier": "", "supplier_url": "", "is_active": "on", "is_silver": "on", "notes": ""}
        response = self.client.post(reverse("tracker:material_add"), data)
        self.assertRedirects(response, reverse("tracker:material_list"))
        order = Material.objects.get(name="Metal clay order")
        self.assertEqual((order.pricing_type, order.base_price, order.markup_percentage, order.is_silver, order.final_price),
                         ("fixed", Decimal("1.0000"), Decimal("0.00"), False, Decimal("1.0000")))

    def test_order_is_typed_as_an_amount(self):
        html = self.client.get(reverse("tracker:class_basket", args=[self.amy.pk])).content.decode()
        self.assertIn("Type the amount", html)
        self.buy(self.order, "12.50")
        self.assertEqual(statements.statement_for(self.amy).items[0]["label"], "Cookson order, £12.50")


class ChooseSilverTests(TestCase):
    def setUp(self):
        self.wire = make_material(name="Oval wire", pricing_type="per_gram", unit_type="gram", base_price=Decimal("2.58"),
                                  pack_quantity=Decimal("1"), markup_percentage=Decimal("5"), price_date=date(2026, 3, 1))
        self.copper = make_material(name="Copper sheet", pricing_type="per_gram", unit_type="gram",
                                    base_price=Decimal("0.20"), pack_quantity=Decimal("1"))
        self.lesson = make_material(name="Lesson", kind="lesson")
        self.url = reverse("tracker:material_silver")

    def test_suggestions_are_ticked_but_not_saved(self):
        response = self.client.get(self.url)
        suggested = [m.name for m in response.context["materials"] if m.suggested]
        self.assertEqual(suggested, ["Oval wire"])
        self.assertNotIn("Lesson", [m.name for m in response.context["materials"]])
        self.assertFalse(Material.objects.get(pk=self.wire.pk).is_silver)

    def test_saving_ticks_recosts_sales_and_can_be_undone(self):
        SilverPrice.objects.create(price_per_kg=Decimal("1000"), fetched_at=at_noon(date(2026, 3, 1)))
        SilverPrice.objects.create(price_per_kg=Decimal("1100"), fetched_at=at_noon(date(2026, 3, 10)))
        sale = Purchase(student=Student.objects.create(name="Amy"), material=self.wire, quantity=Decimal("10"),
                        purchase_date=date(2026, 3, 12))
        sale.set_price(reprice=True)
        sale.save()
        self.assertEqual(sale.unit_cost, Decimal("2.5800"))

        response = self.client.post(self.url, {"silver": [str(self.wire.pk)]})
        self.assertRedirects(response, reverse("tracker:material_list"))
        self.wire.refresh_from_db()
        sale.refresh_from_db()
        self.assertTrue(self.wire.is_silver)
        self.assertEqual(sale.unit_cost, Decimal("2.8380"))  # 2.58 × 1100/1000

        self.client.post(reverse("tracker:undo"), {"id": self.client.session["undo"]["id"]})
        self.wire.refresh_from_db()
        sale.refresh_from_db()
        self.assertEqual((self.wire.is_silver, sale.unit_cost), (False, Decimal("2.5800")))

    def test_unticking_removes_silver(self):
        self.copper.is_silver = True
        self.copper.save()
        self.client.post(self.url, {"silver": []})
        self.copper.refresh_from_db()
        self.assertFalse(self.copper.is_silver)


class DuplicateMaterialTests(TestCase):
    def test_duplicate_prefills_and_saves_a_new_copy(self):
        original = make_material(category=Category.objects.create(name="wire"), supplier="Cooksongold",
                                 sort_order=7, is_silver=True, price_date=date(2026, 3, 1))
        url = reverse("tracker:material_add") + f"?copy={original.pk}"
        form = self.client.get(url).context["form"]
        self.assertEqual(form.initial["name"], "Jump rings (copy)")
        self.assertEqual(form.initial["category_name"], "wire")
        self.assertEqual(form.initial["base_price"], Decimal("5.0000"))

        data = {"name": "Jump rings 6mm", "category_name": "wire", "pricing_type": "fixed", "unit_type": "item",
                "base_price": "5.00", "pack_quantity": "50", "markup_percentage": "25", "supplier": "Cooksongold",
                "supplier_url": "", "is_active": "on", "is_silver": "on", "price_date": "2026-03-01", "notes": ""}
        self.client.post(url, data)
        copy = Material.objects.get(name="Jump rings 6mm")
        self.assertEqual((copy.markup_percentage, copy.sort_order, copy.price_date, copy.category.name),
                         (Decimal("25.00"), 7, date(2026, 3, 1), "wire"))
        original.refresh_from_db()
        self.assertEqual((original.name, original.markup_percentage), ("Jump rings", Decimal("20.00")))
        self.assertFalse(PriceChange.objects.exists())

    def test_material_list_offers_duplicate(self):
        material = make_material()
        self.assertContains(self.client.get(reverse("tracker:material_list")), f"?copy={material.pk}")


class DeliberateMarkupTests(TestCase):
    def test_on_purpose_stops_the_low_markup_flag_and_can_be_undone(self):
        stone = make_material(name="CZ 2mm", markup_percentage=Decimal("0"))
        stud = make_material(name="Studs", markup_percentage=Decimal("5"))
        page = self.client.get(reverse("tracker:material_list"))
        self.assertContains(page, "On purpose")
        self.assertContains(page, "All 2 low markups are on purpose")

        self.client.post(reverse("tracker:material_markup_ok"), {"material": [stone.pk, stud.pk]})
        self.assertEqual(margins.flag_materials(Material.objects.all()), {})
        self.client.post(reverse("tracker:undo"), {"id": self.client.session["undo"]["id"]})
        self.assertEqual(set(margins.flag_materials(Material.objects.all())), {stone.pk, stud.pk})

    def test_deliberate_silver_markup_still_warns_when_selling_at_a_loss(self):
        now = timezone.now()
        wire = make_material(name="Silver wire", pricing_type="per_gram", base_price=Decimal("1.00"),
                             pack_quantity=Decimal("1"), markup_percentage=Decimal("5"), markup_ok=True,
                             is_silver=True, price_date=timezone.localdate() - timedelta(days=20))
        SilverPrice.objects.create(price_per_kg=Decimal("1000"), fetched_at=now - timedelta(days=21))
        SilverPrice.objects.create(price_per_kg=Decimal("1040"), fetched_at=now - timedelta(days=1))
        self.assertEqual(margins.flag_materials([wire]), {})  # 5% markup still covers a 4% rise
        SilverPrice.objects.create(price_per_kg=Decimal("1100"), fetched_at=now)
        self.assertIn("Silver is up 10%", margins.flag_materials([wire])[wire.pk][0])


class DuplicateStudentTests(TestCase):
    def setUp(self):
        self.material = make_material()
        self.old = Student.objects.create(name="Kate", class_name="Previous student", phone="0777")
        self.kate = Student.objects.create(name="Kate", class_name="Thurs 11am")
        Student.objects.create(name="Kate", class_name="Thurs 5pm")
        p = Purchase(student=self.old, material=self.material, quantity=Decimal("10"), purchase_date=date(2026, 3, 1))
        p.set_price(reprice=True)
        p.save()
        Payment.objects.create(student=self.old, amount=Decimal("1"))

    def test_student_choices_show_the_class(self):
        self.assertContains(self.client.get(reverse("tracker:purchase_new")), "Kate – Thurs 11am")

    def test_merge_moves_history_and_can_be_undone(self):
        url = reverse("tracker:student_merge", args=[self.old.pk])
        self.assertEqual(len(self.client.get(url).context["same_name"]), 2)
        preview = self.client.get(url, {"into": ["", str(self.kate.pk)]})
        self.assertEqual(preview.context["into"], self.kate)

        response = self.client.post(url, {"into": self.kate.pk})
        self.assertRedirects(response, self.kate.get_absolute_url())
        self.assertFalse(Student.objects.filter(pk=self.old.pk).exists())
        self.kate.refresh_from_db()
        self.assertEqual((self.kate.purchases.count(), self.kate.payments.count(), self.kate.phone), (1, 1, "0777"))
        self.assertEqual(self.kate.purchases.get().class_name, "Previous student")

        self.client.post(reverse("tracker:undo"), {"id": self.client.session["undo"]["id"]})
        self.old.refresh_from_db()
        self.kate.refresh_from_db()
        self.assertEqual((self.old.purchases.count(), self.old.payments.count()), (1, 1))
        self.assertEqual((self.kate.purchases.count(), self.kate.phone), (0, ""))


WIX_CSV = (
    "Booking ID,First Name,Last Name,Email,Phone,Service\n"
    "1,Sarah,Jones,sarah@example.com,07700 900001,Wed 5pm\n"
    "2,Sarah,Jones,sarah@example.com,07700 900001,Rings course\n"
    "3,Wendy,Hill,wendy@example.com,,Thurs 11am\n"
    "4,Kate,Smith,kate@example.com,,Thurs 11am\n"
    "5,Bob,New,not-an-email,,Wed 5pm\n"
)


class ContactImportTests(TestCase):
    def setUp(self):
        self.sarah = Student.objects.create(name="Sarah Jones", class_name="Wed 5pm", email="old@example.com")
        self.wendy = Student.objects.create(name="Wendy", class_name="Thurs 11am")
        Student.objects.create(name="Kate", class_name="Thurs 11am")
        Student.objects.create(name="Kate", class_name="Thurs 5pm")

    def test_reading_and_matching(self):
        from tracker import contacts_import
        people = contacts_import.read_people(WIX_CSV.encode("utf-8-sig"))
        self.assertEqual([p.name for p in people], ["Sarah Jones", "Wendy Hill", "Kate Smith", "Bob New"])
        self.assertEqual(people[0].booked, ["Wed 5pm", "Rings course"])
        self.assertEqual(people[3].email, "")  # invalid address dropped
        contacts_import.match(people, Student.objects.all())
        sarah, wendy, kate, bob = people
        self.assertEqual((sarah.student, sarah.rename), (self.sarah, False))
        self.assertEqual((wendy.student, wendy.action, wendy.rename), (self.wendy, str(self.wendy.pk), True))
        self.assertEqual((kate.action, len(kate.candidates)), ("skip", 2))
        self.assertEqual(bob.action, "new")

    def test_rejects_files_without_names(self):
        from tracker import contacts_import
        with self.assertRaises(ValueError):
            contacts_import.read_people(b"Email\nx@example.com\n")

    def test_upload_preview_then_import(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        upload = SimpleUploadedFile("wix.csv", WIX_CSV.encode(), content_type="text/csv")
        preview = self.client.post(reverse("tracker:student_import"), {"file": upload})
        self.assertEqual(len(preview.context["people"]), 4)
        self.assertContains(preview, "Wendy – Thurs 11am")

        response = self.client.post(reverse("tracker:student_import"), {
            "apply": "1", "new_class": "Wed 5pm",
            "action_0": str(self.sarah.pk), "action_1": str(self.wendy.pk), "rename_1": "1",
            "action_2": "skip", "action_3": "new",
        })
        self.assertRedirects(response, reverse("tracker:student_list"))
        self.sarah.refresh_from_db()
        self.wendy.refresh_from_db()
        self.assertEqual((self.sarah.email, self.sarah.phone), ("old@example.com", "07700 900001"))  # email kept
        self.assertEqual((self.wendy.name, self.wendy.email), ("Wendy Hill", "wendy@example.com"))
        self.assertEqual(Student.objects.get(name="Bob New").class_name, "Wed 5pm")

        self.client.post(reverse("tracker:undo"), {"id": self.client.session["undo"]["id"]})
        self.wendy.refresh_from_db()
        self.assertEqual((self.wendy.name, self.wendy.email), ("Wendy", ""))
        self.assertFalse(Student.objects.filter(name="Bob New").exists())

    def test_apply_without_upload_asks_again(self):
        response = self.client.post(reverse("tracker:student_import"), {"apply": "1"})
        self.assertRedirects(response, reverse("tracker:student_import"))


class TermDatesTests(TestCase):
    def setUp(self):
        self.prev = StudioClass.objects.create(name="Previous student")
        self.autumn = StudioClass.objects.create(name="Autumn", start_date=date(2026, 9, 1))
        Student.objects.create(name="Old timer", class_name="Previous student")
        self.url = reverse("tracker:class_dates")

    def test_end_date_for_several_classes_makes_them_finished(self):
        self.assertEqual(self.client.get(reverse("tracker:class_list")).context["n_candidates"], 0)
        response = self.client.post(self.url, {"studio_class": [self.prev.pk, self.autumn.pk], "end": "2026-10-01"})
        self.assertRedirects(response, reverse("tracker:class_list"))
        self.prev.refresh_from_db()
        self.autumn.refresh_from_db()
        self.assertEqual((self.prev.status, self.autumn.start_date), ("finished", date(2026, 9, 1)))
        self.assertEqual(self.client.get(reverse("tracker:class_list")).context["n_candidates"], 1)

    def test_rejects_end_before_existing_start_and_needs_a_class(self):
        response = self.client.post(self.url, {"studio_class": [self.autumn.pk], "end": "2026-08-01"})
        self.assertContains(response, "before it starts")
        self.assertContains(self.client.post(self.url, {"end": "2026-08-01"}), "Tick at least one class.")
        self.assertContains(self.client.post(self.url, {"studio_class": [self.prev.pk]}), "Enter a start date")
