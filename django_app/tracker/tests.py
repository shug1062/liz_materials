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

from . import suppliers
from .models import Category, ClassOrder, Material, Payment, PriceChange, Project, Purchase, SilverPrice, Student


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
