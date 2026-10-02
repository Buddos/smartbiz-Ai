from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from barber.models import Appointment, BarberService
from businesses.models import Business
from sales.models import Sale, SaleItem

from .models import Product


class BarberProductPageTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Retail Barbershop",
            business_type="BARBER",
            email="products@example.com",
            phone_number="0700000000",
        )
        self.owner = User.objects.create_user(
            email="products-owner@example.com",
            password="test-password",
            role="OWNER",
            business=self.business,
        )
        self.product = Product.objects.create(
            business=self.business,
            name="Beard Oil",
            sku="OIL-001",
            purchase_price=180,
            selling_price=400,
            current_stock=6,
            reorder_level=10,
            created_by=self.owner,
        )
        BarberService.objects.create(
            business=self.business,
            name="Haircut",
            price=350,
        )
        self.client.force_login(self.owner)

    def test_barber_products_page_and_live_data_include_inventory(self):
        page_response = self.client.get(reverse("products:list"))
        live_response = self.client.get(reverse("products:api_live_barber_products"))

        self.assertEqual(page_response.status_code, 200)
        self.assertContains(page_response, "Attach rate by barber")
        self.assertContains(page_response, "Add product")
        self.assertEqual(live_response.status_code, 200)
        self.assertEqual([row["name"] for row in live_response.json()["products"]], ["Beard Oil"])
        self.assertEqual(live_response.json()["metrics"]["low_stock_count"], 1)

    def test_restock_and_archive_actions_update_live_inventory(self):
        restock_response = self.client.post(reverse(
            "products:barber_product_action",
            kwargs={"product_id": self.product.id},
        ), {"action": "restock", "quantity": "5"})
        self.assertEqual(restock_response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, 11)

        archive_response = self.client.post(reverse(
            "products:barber_product_action",
            kwargs={"product_id": self.product.id},
        ), {"action": "archive"})
        self.assertEqual(archive_response.status_code, 200)
        self.product.refresh_from_db()
        self.assertFalse(self.product.is_active)

        live_response = self.client.get(reverse("products:api_live_barber_products"), {"status": "ARCHIVED"})
        self.assertEqual(live_response.json()["products"][0]["state"], "archived")

    def test_live_product_metrics_use_paid_sales_and_linked_completed_visits(self):
        barber = User.objects.create_user(
            email="sales-barber@example.com",
            password="test-password",
            first_name="Marcus",
            role="BARBER",
            business=self.business,
        )
        service = BarberService.objects.get(business=self.business)
        sale = Sale.objects.create(
            business=self.business,
            sale_number="INV-BARBER-001",
            barber=barber,
            created_by=self.owner,
            customer_name="Brian",
            subtotal=400,
            amount_paid=400,
            payment_method="CASH",
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            product_name=self.product.name,
            product_sku=self.product.sku,
            unit_price=400,
            cost_price=180,
            quantity=1,
        )
        sale.recalculate()
        Appointment.objects.create(
            business=self.business,
            client_name="Brian",
            service=service,
            barber=barber,
            sale=sale,
            status="DONE",
            completed_at=timezone.now(),
        )

        response = self.client.get(reverse("products:api_live_barber_products"))

        data = response.json()
        self.assertEqual(data["metrics"]["revenue"], 400)
        self.assertEqual(data["metrics"]["units"], 1)
        self.assertEqual(data["metrics"]["margin"], 55)
        self.assertEqual(data["metrics"]["attach_rate"], 100)
        self.assertEqual(data["barber_rates"][0]["rate"], 100)
        self.assertEqual(data["products"][0]["profit_30d"], 220)


class SalonRetailProductPageTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Rose Salon Retail",
            business_type="SALON",
            email="salon-products@example.com",
            phone_number="0700000001",
        )
        self.owner = User.objects.create_user(
            email="salon-products-owner@example.com",
            password="test-password",
            role="OWNER",
            business=self.business,
        )
        self.product = Product.objects.create(
            business=self.business,
            name="Moisture Shampoo",
            sku="SALON-RET-001",
            purchase_price=350,
            selling_price=700,
            current_stock=2,
            reorder_level=5,
            created_by=self.owner,
        )
        Product.objects.create(
            business=self.business,
            name="Wash and style",
            sku="SALON-SVC-001",
            selling_price=1200,
            current_stock=0,
            created_by=self.owner,
            metadata={"salon_service": True, "duration_min": 45},
        )
        self.client.force_login(self.owner)

    def test_salon_retail_catalog_shows_saved_inventory_not_services(self):
        response = self.client.get(reverse("products:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Retail products")
        self.assertContains(response, "Moisture Shampoo")
        self.assertNotContains(response, "Wash and style")
        self.assertEqual(response.context["product_count"], 1)
        self.assertEqual(response.context["low_stock_count"], 1)
        self.assertEqual(response.context["out_of_stock_count"], 0)
        self.assertEqual(response.context["total_stock_value"], 700)

        low_stock_response = self.client.get(reverse("products:list"), {"stock": "low"})
        self.assertContains(low_stock_response, "Moisture Shampoo")

    def test_salon_catalog_does_not_leak_products_from_another_business(self):
        other_business = Business.objects.create(
            name="Other Salon",
            business_type="SALON",
            email="other-products@example.com",
            phone_number="0700000002",
        )
        Product.objects.create(
            business=other_business,
            name="Private Stock",
            sku="OTHER-RET-001",
            current_stock=10,
            created_by=self.owner,
        )

        response = self.client.get(reverse("products:list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Moisture Shampoo")
        self.assertNotContains(response, "Private Stock")
