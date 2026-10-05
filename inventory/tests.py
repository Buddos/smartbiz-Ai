from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from businesses.models import Business


class StockCountPageTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Stock Count Shop",
            business_type="RETAIL",
            email="stock-counts@example.com",
            phone_number="0700000000",
        )
        self.user = User.objects.create_user(
            email="stock-count-owner@example.com",
            password="test-password",
            role="OWNER",
            business=self.business,
        )
        self.client.force_login(self.user)

    def test_stock_count_page_renders_with_registered_business_layout_tag(self):
        response = self.client.get(reverse("inventory:stock_counts"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stock Counts")
