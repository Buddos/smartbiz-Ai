from django.test import TestCase
from django.urls import reverse
from types import SimpleNamespace
from unittest.mock import patch

from accounts.models import User
from businesses.models import Business
from analytics.models import BusinessInsight
from inventory.models import InventoryAlert
from products.models import Product


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
        self.assertNotContains(response, 'id="electronicsSidebar"')
        self.assertNotContains(response, 'class="electronics-main"')

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
