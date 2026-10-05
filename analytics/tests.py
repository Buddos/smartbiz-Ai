from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from accounts.models import User
from businesses.models import Business
from analytics.models import BusinessInsight
from inventory.models import InventoryAlert
from products.models import Product
from sales.models import Sale, SaleItem


class GenerateInsightsViewTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Insight Test Shop",
            business_type="ELECTRONICS",
            email="insights@example.com",
            phone_number="0700000000",
        )
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="test-password",
            role="OWNER",
            business=self.business,
        )
        self.client.force_login(self.owner)

    @patch(
        "analytics.views.generate_ai_engine_review",
        return_value=([], SimpleNamespace(title="Gemini business review")),
    )
    def test_generating_insights_uses_gemini_and_redirects_to_dashboard(self, generate_review):
        response = self.client.post(reverse("analytics:generate_insights"))

        self.assertRedirects(response, reverse("analytics:dashboard"))
        generate_review.assert_called_once_with(self.business)
        self.assertEqual(len(list(response.wsgi_request._messages)), 1)


class DashboardNotificationsTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Notification Test Shop",
            business_type="ELECTRONICS",
            email="notifications@example.com",
            phone_number="0700000000",
        )
        self.owner = User.objects.create_user(
            email="notifications-owner@example.com",
            password="test-password",
            role="OWNER",
            business=self.business,
        )
        self.client.force_login(self.owner)

    def test_dashboard_bell_displays_real_unread_insights_and_active_alerts(self):
        BusinessInsight.objects.create(
            business=self.business,
            insight_type="RISK",
            title="Sales are declining",
            description="Sales are lower than the previous period.",
        )
        product = Product.objects.create(
            business=self.business,
            name="Notification handset",
            sku="NOTIFY-001",
            created_by=self.owner,
        )
        InventoryAlert.objects.create(
            business=self.business,
            product=product,
            alert_type="LOW_STOCK",
            message="Only two units remain.",
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-notifications-toggle')
        self.assertContains(response, "dashboard-readable")
        self.assertContains(response, "Sales are declining")
        self.assertContains(response, "Notification handset")
        self.assertContains(response, "Only two units remain.")
        self.assertContains(response, "2 items need attention")

    def test_notification_bell_is_present_across_dashboard_types(self):
        for business_type in ("ELECTRONICS", "SALON", "BARBER", "RETAIL"):
            with self.subTest(business_type=business_type):
                self.business.business_type = business_type
                self.business.save(update_fields=["business_type"])
                response = self.client.get(reverse("dashboard"))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'data-notifications-toggle')

    def test_business_admin_dashboard_has_notification_bell(self):
        response = self.client.get(reverse("business_admin"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-notifications-toggle')
        self.assertContains(response, 'class="admin-sidebar"')
        settings_url = f'{reverse("businesses:settings")}?from=admin'
        self.assertContains(response, f'href="{settings_url}"')
        self.assertNotContains(response, 'id="electronicsSidebar"')
        self.assertNotContains(response, 'class="electronics-main"')

    def test_account_menu_links_business_admin_for_each_dashboard_type(self):
        admin_url = reverse("business_admin")
        for business_type in ("ELECTRONICS", "RETAIL", "RESTAURANT", "SALON", "BARBER"):
            with self.subTest(business_type=business_type):
                self.business.business_type = business_type
                self.business.save(update_fields=["business_type"])
                response = self.client.get(reverse("dashboard"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'href="{admin_url}"')
                self.assertContains(response, "Personal settings")
                self.assertNotContains(
                    response,
                    f'href="{reverse("businesses:settings")}"',
                )

    def test_business_settings_stay_inside_business_admin_navigation(self):
        settings_url = f'{reverse("businesses:settings")}?from=admin'
        response = self.client.get(reverse("businesses:settings"))
        self.assertRedirects(response, settings_url)

        response = self.client.get(settings_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="admin-sidebar"')
        self.assertContains(response, "Business admin")
        self.assertContains(
            response,
            f'action="{reverse("businesses:capabilities_save")}?from=admin"',
        )

        response = self.client.post(
            f'{reverse("businesses:capabilities_save")}?from=admin&section=capabilities',
            {"capabilities": self.business.enabled_capabilities},
        )
        self.assertRedirects(
            response,
            f'{reverse("businesses:settings")}?from=admin&section=capabilities',
        )

    def test_business_admin_navigation_keeps_its_sidebar_on_destination_pages(self):
        destinations = (
            "accounts:users_list",
            "products:list",
            "inventory:alerts",
            "businesses:settings",
            "analytics:financial",
            "reports:list",
            "accounts:settings",
        )

        for route_name in destinations:
            with self.subTest(route_name=route_name):
                response = self.client.get(f"{reverse(route_name)}?from=admin")

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="admin-sidebar"')
                self.assertNotContains(response, 'id="electronicsSidebar"')
                self.assertNotContains(response, "Back to Administration")


class RestaurantDashboardTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Green Plate",
            business_type="RESTAURANT",
            email="green-plate@example.com",
            phone_number="0700000000",
        )
        self.user = User.objects.create_user(
            email="restaurant-owner@example.com",
            password="RestaurantPass1!",
            role="OWNER",
            business=self.business,
        )
        self.product = Product.objects.create(
            business=self.business,
            name="Pilau",
            sku="PILAU-001",
            purchase_price=Decimal("50.00"),
            selling_price=Decimal("120.00"),
            current_stock=2,
            reorder_level=5,
        )
        self.client.force_login(self.user)

    def test_restaurant_dashboard_shows_real_empty_state_and_operation_navigation(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "analytics/restaurant_dashboard.html")
        self.assertContains(response, "Green Plate")
        self.assertContains(response, "No orders have been recorded today.")
        self.assertContains(response, "No completed menu sales recorded today.")
        self.assertContains(response, "Kitchen Display")
        self.assertContains(response, "Tables")
        self.assertContains(response, "Reservations")
        self.assertContains(response, "Recipes")
        self.assertContains(response, 'data-restaurant-live')
        self.assertContains(response, 'class="restaurant-app-shell dashboard-readable"')
        self.assertContains(response, "Business admin")
        self.assertEqual(response.context["restaurant_dashboard"]["today_revenue"], 0)

    def test_existing_restaurant_pages_keep_the_restaurant_navigation(self):
        for route_name in (
            "sales:list",
            "sales:create",
            "restaurant:tables",
            "restaurant:reservations",
            "restaurant:kitchen",
            "restaurant:menu",
            "restaurant:ingredients",
            "restaurant:recipes",
            "restaurant:suppliers",
            "restaurant:cash_drawer",
            "restaurant:food_cost",
            "products:list",
            "inventory:dashboard",
            "inventory:transaction_create",
            "customers:list",
            "expenses:list",
            "ai_engine:assistant",
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="restaurantSidebar"')

    def test_live_api_reports_only_saved_restaurant_sales_and_stock(self):
        completed_sale = Sale.objects.create(
            business=self.business,
            sale_number="REST-001",
            sale_date=timezone.now(),
            customer_name="Diner",
            subtotal=Decimal("100.00"),
            total=Decimal("100.00"),
            order_status="COMPLETED",
            metadata={"table_reference": "Table 3"},
        )
        SaleItem.objects.create(
            sale=completed_sale,
            product=self.product,
            product_name="Pilau",
            product_sku=self.product.sku,
            unit_price=Decimal("100.00"),
            cost_price=Decimal("50.00"),
            quantity=1,
        )
        Sale.objects.create(
            business=self.business,
            sale_number="REST-002",
            sale_date=timezone.now(),
            total=Decimal("30.00"),
            order_status="PROCESSING",
        )
        Sale.objects.create(
            business=self.business,
            sale_number="REST-003",
            sale_date=timezone.now(),
            total=Decimal("900.00"),
            order_status="CANCELLED",
        )
        another_business = Business.objects.create(
            name="Another restaurant",
            business_type="RESTAURANT",
            email="another-restaurant@example.com",
            phone_number="0711111111",
        )
        Sale.objects.create(
            business=another_business,
            sale_number="OTHER-001",
            sale_date=timezone.now(),
            total=Decimal("700.00"),
            order_status="COMPLETED",
        )

        response = self.client.get(reverse("analytics:restaurant_dashboard_data"))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["today_revenue"], "100")
        self.assertEqual(data["completed_orders"], 1)
        self.assertEqual(data["open_orders"], 1)
        self.assertEqual(data["low_stock_count"], 1)
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(data["top_items"][0]["product_name"], "Pilau")
        self.assertEqual(
            {order["number"] for order in data["recent_orders"]},
            {"REST-001", "REST-002"},
        )
        completed_order = next(
            order for order in data["recent_orders"]
            if order["number"] == "REST-001"
        )
        self.assertEqual(completed_order["table_reference"], "Table 3")

    def test_restaurant_live_data_api_is_not_available_for_other_business_types(self):
        self.business.business_type = "RETAIL"
        self.business.save(update_fields=["business_type"])

        response = self.client.get(reverse("analytics:restaurant_dashboard_data"))

        self.assertEqual(response.status_code, 404)
