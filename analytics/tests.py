from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch

from accounts.models import User
from businesses.models import Business
from analytics.models import BusinessInsight
from ai_engine.models import AIInsight
from customers.models import Customer
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

    @patch("analytics.views.run_intelligence_pipeline", return_value=[])
    def test_generating_insights_uses_smartbiz_ai_engine(self, run_pipeline):
        response = self.client.post(reverse("analytics:generate_insights"))

        self.assertRedirects(response, reverse("analytics:dashboard"))
        run_pipeline.assert_called_once_with(self.business)
        self.assertEqual(
            [message.message for message in response.wsgi_request._messages],
            ["Your AI insights are up to date. New insights appear when business data changes."],
        )

    @patch("ai_engine.views.run_intelligence_pipeline", return_value=[])
    def test_ai_insights_page_generate_action_uses_same_engine(self, run_pipeline):
        response = self.client.post(reverse("ai_engine:generate"))

        self.assertRedirects(response, reverse("ai_engine:home"))
        run_pipeline.assert_called_once_with(self.business)


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
        AIInsight.objects.create(
            business=self.business,
            insight_type="SALES",
            title="Sales are improving",
            observation="Sales increased this week.",
            interpretation="Keep the promotion running.",
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-notifications-toggle')
        self.assertContains(response, 'data-assistant-widget-toggle')
        self.assertContains(response, 'data-smartbiz-assistant-frame')
        self.assertContains(response, "dashboard-readable")
        self.assertContains(response, "Sales are declining")
        self.assertContains(response, "Notification handset")
        self.assertContains(response, "Only two units remain.")
        self.assertContains(response, "Sales are improving")
        self.assertContains(response, "Keep the promotion running.")
        self.assertContains(response, "3 items need attention")

    def test_notification_bell_displays_all_active_alerts_not_only_five(self):
        product = Product.objects.create(
            business=self.business,
            name="Notification stock",
            sku="NOTIFY-ALL",
            created_by=self.owner,
        )
        alert_types = ("LOW_STOCK", "OUT_OF_STOCK", "EXPIRY", "SLOW_MOVING", "OVERSTOCKED")
        for index in range(7):
            InventoryAlert.objects.create(
                business=self.business,
                product=product,
                alert_type=alert_types[index % len(alert_types)],
                message=f"Alert number {index + 1}.",
            )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        for index in range(7):
            self.assertContains(response, f"Alert number {index + 1}.")
        self.assertContains(response, "7 items need attention")

    def test_notification_bell_is_present_across_dashboard_types(self):
        for business_type in ("ELECTRONICS", "SALON", "BARBER", "RETAIL", "HARDWARE"):
            with self.subTest(business_type=business_type):
                self.business.business_type = business_type
                self.business.save(update_fields=["business_type"])
                response = self.client.get(reverse("dashboard"))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'data-notifications-toggle')
                self.assertContains(response, 'data-assistant-widget-toggle')

    def test_full_assistant_page_does_not_show_duplicate_widget_launcher(self):
        response = self.client.get(reverse("ai_engine:assistant"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-smartbiz-assistant-frame')
        self.assertNotContains(response, 'data-assistant-widget-toggle')

    def test_business_admin_dashboard_has_notification_bell(self):
        response = self.client.get(reverse("business_admin"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-notifications-toggle')
        self.assertContains(response, 'class="admin-sidebar"')
        settings_url = f'{reverse("businesses:settings")}?from=admin'
        self.assertContains(response, f'href="{settings_url}"')
        self.assertNotContains(response, 'id="electronicsSidebar"')


class HardwareDashboardTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Northside Hardware",
            business_type="HARDWARE",
            email="hardware@example.com",
            phone_number="0700000000",
        )
        self.owner = User.objects.create_user(
            email="hardware-owner@example.com",
            password="test-password",
            first_name="Hardware",
            role="OWNER",
            business=self.business,
        )
        self.client.force_login(self.owner)

    def test_dashboard_uses_hardware_navigation_and_live_shop_data(self):
        low_stock_product = Product.objects.create(
            business=self.business,
            name="Roofing screws",
            sku="SCREW-001",
            current_stock=2,
            reorder_level=5,
        )
        Sale.objects.create(
            business=self.business,
            sale_number="HARDWARE-001",
            customer_name="Local contractor",
            subtotal=Decimal("350.00"),
            total=Decimal("350.00"),
            amount_paid=Decimal("100.00"),
            balance_due=Decimal("250.00"),
            payment_method="CREDIT",
            payment_status="PARTIAL",
            order_status="COMPLETED",
            created_by=self.owner,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "hardware/dashboard.html")
        self.assertEqual(response.context["hardware_dashboard"]["receivables"], Decimal("250.00"))
        self.assertEqual(response.context["hardware_dashboard"]["low_stock_products"][0], low_stock_product)
        self.assertContains(response, "POS")
        self.assertContains(response, "Credit Ledger")
        self.assertContains(response, "Purchase Orders")
        self.assertContains(response, "Roofing screws")
        self.assertContains(response, 'data-hardware-live="dashboard"')
        self.assertNotContains(response, 'class="electronics-main"')
        self.assertContains(response, f'href="{reverse("business_admin")}"')
        self.assertContains(response, "Settings")
        self.assertContains(response, "Profile")
        self.assertContains(response, "Log out")
        self.assertNotContains(response, 'class="hardware-topbar-pos"')

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


class WholesaleDashboardTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Wholesale Test Co",
            business_type="WHOLESALE",
            email="wholesale@example.com",
            phone_number="0700000000",
        )
        self.user = User.objects.create_user(
            email="wholesale-owner@example.com",
            password="test-password",
            role="OWNER",
            business=self.business,
        )
        self.customer = Customer.objects.create(
            business=self.business,
            name="Market Buyer",
        )
        self.product = Product.objects.create(
            business=self.business,
            name="Cooking oil case",
            sku="OIL-CASE",
            purchase_price=Decimal("50.00"),
            selling_price=Decimal("75.00"),
            wholesale_price=Decimal("65.00"),
            current_stock=3,
            reorder_level=5,
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def test_dashboard_shows_wholesale_navigation_and_live_metrics(self):
        Sale.objects.create(
            business=self.business,
            sale_number="WHOLESALE-001",
            customer=self.customer,
            sale_date=timezone.now(),
            subtotal=Decimal("100.00"),
            amount_paid=Decimal("25.00"),
            payment_method="CREDIT",
            order_status="PENDING",
            created_by=self.user,
        )
        Sale.objects.create(
            business=self.business,
            sale_number="WHOLESALE-002",
            customer=self.customer,
            sale_date=timezone.now() - timedelta(days=45),
            subtotal=Decimal("200.00"),
            payment_method="CREDIT",
            order_status="SHIPPED",
            created_by=self.user,
        )

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "analytics/wholesale_dashboard.html")
        self.assertContains(response, 'data-wholesale-dashboard')
        self.assertEqual(response.content.count(b'class="wholesale-sidebar"'), 1)
        self.assertEqual(response.content.count(b'class="wholesale-topbar"'), 1)
        self.assertContains(response, "Wholesale workspace")
        self.assertContains(response, "Sales Reps")
        self.assertContains(response, "Purchase Orders")
        self.assertContains(response, "Accounts Receivable")
        self.assertContains(response, "Promotions")
        self.assertContains(response, 'data-metric="today_sales"')
        self.assertEqual(response.context["wholesale_dashboard"]["today_sales"], Decimal("100.00"))
        self.assertEqual(response.context["wholesale_dashboard"]["outstanding_ar"], Decimal("275.00"))
        self.assertEqual(response.context["wholesale_dashboard"]["overdue_ar"], Decimal("200.00"))
        self.assertEqual(response.context["wholesale_dashboard"]["low_stock_skus"], 1)

    def test_live_api_returns_only_current_business_data(self):
        Sale.objects.create(
            business=self.business,
            sale_number="WHOLESALE-API-001",
            customer=self.customer,
            sale_date=timezone.now(),
            subtotal=Decimal("100.00"),
            amount_paid=Decimal("25.00"),
            payment_method="CREDIT",
            order_status="PENDING",
            created_by=self.user,
        )
        other_business = Business.objects.create(
            name="Other Wholesale Co",
            business_type="WHOLESALE",
            email="other-wholesale@example.com",
            phone_number="0711111111",
        )
        Sale.objects.create(
            business=other_business,
            sale_number="OTHER-WHOLESALE-001",
            sale_date=timezone.now(),
            subtotal=Decimal("999.00"),
            order_status="COMPLETED",
        )

        response = self.client.get(reverse("analytics:wholesale_dashboard_data"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.json()["today_sales"]), Decimal("100.00"))
        self.assertEqual(response.json()["orders_today"], 1)
        self.assertEqual(response.json()["pending_orders"], 1)
        self.assertEqual(response.json()["low_stock_skus"], 1)
        self.assertIn("no-store", response["Cache-Control"])

    def test_live_api_is_unavailable_to_other_business_types(self):
        self.business.business_type = "RETAIL"
        self.business.save(update_fields=["business_type"])

        response = self.client.get(reverse("analytics:wholesale_dashboard_data"))

        self.assertEqual(response.status_code, 404)

    def test_wholesale_navigation_destinations_stay_in_the_wholesale_shell(self):
        route_names = (
            "sales:list",
            "sales:create",
            "customers:list",
            "accounts:users_list",
            "products:list",
            "inventory:dashboard",
            "retail:suppliers",
            "retail:credit",
            "expenses:list",
            "analytics:financial",
            "ai_engine:home",
            "ai_engine:assistant",
            "reports:list",
        )
        for route_name in route_names:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="wholesale-sidebar"')
