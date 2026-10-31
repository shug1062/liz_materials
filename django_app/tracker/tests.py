import sqlite3
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import statements, suppliers
from .models import (
    Category, ClassOrder, Material, Payment, PriceChange, Project, Purchase, SilverPrice, Student, estimated_unit_cost,
)


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
        for name in ["dashboard", "student_list", "payments_report", "material_list", "purchase_new", "payment_new"]:
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(f"tracker:{name}")).status_code, 200)
        self.assertEqual(self.client.get(self.student.get_absolute_url()).status_code, 200)

    def test_record_purchase_locks_in_price(self):
        response = self.client.post(reverse("tracker:purchase_new"), {
            "student": self.student.pk, "material": self.material.pk, "quantity": "10",
            "purchase_date": "2026-10-31", "notes": "",
        })
        self.assertRedirects(response, self.student.get_absolute_url())
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
        self.assertRedirects(response, self.student.get_absolute_url())

    def test_payments_report_filters_sales(self):
        shop = Student.objects.create(name="Craft fair", is_sales_channel=True)
        Payment.objects.create(student=self.student, amount=Decimal("5"))
        Payment.objects.create(student=shop, amount=Decimal("40"), payment_method="Card")
        response = self.client.get(reverse("tracker:payments_report"), {"group": "sales"})
        self.assertEqual(response.context["totals"]["total"], Decimal("40"))
        self.assertEqual(response.context["totals"]["card"], Decimal("40"))


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
        self.assertEqual(ClassOrder.ordered_class_names(), ["Tue", "Mon"])


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
                               'href="/profit/"', "Profit"]:
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
        response = self.client.get(reverse("tracker:profit_report"))
        total = response.context["total"]
        self.assertEqual((total["sales"], total["cost"], total["profit"]), (Decimal("7.20"), Decimal("6.00"), Decimal("1.20")))
        self.assertEqual([r["label"] for r in response.context["by_class"]], ["Wed", "Tue"])
        self.assertEqual(len(response.context["by_month"]), 2)

        october = self.client.get(reverse("tracker:profit_report"), {"start": "2026-10-01"}).context["total"]
        self.assertEqual(october["profit"], Decimal("1.00"))

    def test_import_marks_legacy_costs_as_estimates(self):
        Material.objects.all().delete()  # import only runs into an empty database
        with tempfile.NamedTemporaryFile(suffix=".db") as legacy:
            db = sqlite3.connect(legacy.name)
            db.executescript("""
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
