from datetime import timedelta
from decimal import Decimal
from unittest.mock import ANY, MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from businesses.models import Business
from expenses.models import Expense, ExpenseCategory
from products.models import Product
from sales.models import Sale, SaleItem

from .gemini import (
    GeminiNotConfiguredError,
    _business_summary,
    _gemini_text,
    answer_business_question,
    generate_business_review,
)
from .models import AIRecommendation
from .models import AIQuery


class GeminiBusinessReviewTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Fresh Market",
            email="market@example.com",
            phone_number="0700000000",
            currency="KES",
        )
        today = timezone.localdate()
        self.product = Product.objects.create(
            business=self.business,
            name="Green Tea",
            sku="GREEN-TEA",
            purchase_price=Decimal("40.00"),
            selling_price=Decimal("65.00"),
            current_stock=2,
            reorder_level=5,
        )
        sale = Sale.objects.create(
            business=self.business,
            sale_number="GEMINI-001",
            sale_date=timezone.now() - timedelta(days=1),
            subtotal=Decimal("130.00"),
            total=Decimal("130.00"),
            order_status="COMPLETED",
        )
        SaleItem.objects.create(
            sale=sale,
            product=self.product,
            product_name=self.product.name,
            quantity=2,
            unit_price=Decimal("65.00"),
            cost_price=Decimal("40.00"),
            tax_rate=Decimal("0.00"),
            discount=Decimal("0.00"),
            subtotal=Decimal("130.00"),
            total=Decimal("130.00"),
        )
        category = ExpenseCategory.objects.create(
            business=self.business,
            name="Utilities",
        )
        Expense.objects.create(
            business=self.business,
            category=category,
            title="Electricity",
            vendor="Private Vendor",
            notes="Private note",
            amount=Decimal("25.00"),
            expense_date=today,
        )

    def test_summary_uses_fresh_scoped_aggregates_without_customer_or_vendor_details(self):
        other_business = Business.objects.create(
            name="Different Shop",
            email="other@example.com",
            phone_number="0711111111",
        )
        Sale.objects.create(
            business=other_business,
            sale_number="OTHER-001",
            subtotal=Decimal("999.00"),
            total=Decimal("999.00"),
            order_status="COMPLETED",
        )

        summary = _business_summary(self.business)

        self.assertEqual(summary["sales"]["current_30_days_revenue"], 130.0)
        self.assertEqual(summary["sales"]["top_products_by_revenue"][0]["product"], "Green Tea")
        self.assertEqual(summary["expenses"]["current_30_days_total"], 25.0)
        self.assertEqual(summary["expenses"]["largest_categories"][0]["category"], "Utilities")
        self.assertEqual(summary["inventory"]["low_stock_products"], 1)
        self.assertNotIn("Private Vendor", str(summary))
        self.assertNotIn("Private note", str(summary))
        self.assertNotIn("999.0", str(summary))

    @override_settings(GEMINI_API_KEY="")
    def test_missing_server_key_fails_explicitly(self):
        with self.assertRaises(GeminiNotConfiguredError):
            _gemini_text("test prompt")

    @override_settings(GEMINI_API_KEY="configured-on-server", GEMINI_MODEL="gemini-test")
    @patch("google.genai.Client")
    def test_sdk_call_uses_gemini_generate_content_and_closes_client(self, mocked_client):
        mocked_client.return_value.models.generate_content.return_value = MagicMock(
            text="Structured response"
        )

        answer = _gemini_text("test prompt", response_mime_type="application/json")

        self.assertEqual(answer, "Structured response")
        mocked_client.assert_called_once()
        self.assertEqual(mocked_client.call_args.kwargs["api_key"], "configured-on-server")
        mocked_client.return_value.models.generate_content.assert_called_once_with(
            model="gemini-test",
            contents="test prompt",
            config=ANY,
        )
        self.assertEqual(
            mocked_client.return_value.models.generate_content.call_args.kwargs[
                "config"
            ].response_mime_type,
            "application/json",
        )
        mocked_client.return_value.close.assert_called_once_with()

    @override_settings(GEMINI_API_KEY="configured-on-server")
    @patch("ai_engine.gemini._json_response")
    def test_gemini_review_is_saved_as_an_ai_insight_and_recommendation(self, mocked_json):
        mocked_json.return_value = {
            "title": "Review tea stock",
            "summary": "Recent tea sales are recorded in the selected period.",
            "key_findings": ["Stock is below the configured reorder level."],
            "recommendation": "Review supplier lead time before placing an order.",
        }

        insight = generate_business_review(self.business)

        self.assertEqual(insight.source, "AI")
        self.assertEqual(insight.metadata["sales"]["current_30_days_revenue"], 130.0)
        self.assertEqual(
            AIRecommendation.objects.get(related_insight=insight).suggestion,
            "Review supplier lead time before placing an order.",
        )

    @override_settings(GEMINI_API_KEY="configured-on-server")
    @patch("ai_engine.gemini._gemini_text", return_value="Sales were KES 130 in the last 30 days.")
    def test_assistant_uses_gemini_prompt_with_current_business_metrics(self, mocked_gemini):
        answer = answer_business_question(self.business, "How were sales?")

        self.assertIn("KES 130", answer)
        prompt = mocked_gemini.call_args.args[0]
        self.assertIn('"current_30_days_revenue": 130.0', prompt)
        self.assertIn("How were sales?", prompt)
        self.assertNotIn("Private Vendor", prompt)


class AssistantPageTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Assistant Test Shop",
            email="assistant@example.com",
            phone_number="0700000000",
        )
        self.user = User.objects.create_user(
            email="assistant-owner@example.com",
            password="test-password",
            role="OWNER",
            business=self.business,
        )
        self.client.force_login(self.user)

    @override_settings(GEMINI_API_KEY="configured-on-server")
    def test_assistant_page_renders_prompt_chips_composer_and_assets(self):
        response = self.client.get(reverse("ai_engine:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ask SmartBiz AI")
        self.assertContains(response, "Compare my sales")
        self.assertContains(response, "Check stock risks")
        self.assertContains(response, 'data-ai-composer')
        self.assertContains(response, "css/ai-assistant.css")
        self.assertContains(response, "js/ai-assistant.js")

    def test_recent_assistant_messages_render_in_chronological_order(self):
        first = AIQuery.objects.create(
            business=self.business,
            user=self.user,
            question="First question",
            answer="First answer",
        )
        second = AIQuery.objects.create(
            business=self.business,
            user=self.user,
            question="Second question",
            answer="Second answer",
        )
        AIQuery.objects.filter(pk=first.pk).update(
            created_at=timezone.now() - timedelta(minutes=2)
        )
        AIQuery.objects.filter(pk=second.pk).update(
            created_at=timezone.now() - timedelta(minutes=1)
        )

        response = self.client.get(reverse("ai_engine:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First question")
        self.assertContains(response, "Second answer")
        self.assertLess(
            response.content.index(b"First question"),
            response.content.index(b"Second question"),
        )

    def test_assistant_sidebar_route_redirects_to_assistant_section(self):
        response = self.client.get(reverse("ai_engine:assistant"))

        self.assertRedirects(
            response,
            f"{reverse('ai_engine:home')}#assistant",
            fetch_redirect_response=False,
        )
