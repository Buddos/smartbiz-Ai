from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import ANY, MagicMock, patch

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from google.genai.errors import APIError

from accounts.models import User
from businesses.models import Business
from expenses.models import Expense, ExpenseCategory
from products.models import Product
from sales.models import Sale, SaleItem

from .gemini import (
    GeminiNotConfiguredError,
    GeminiRequestError,
    _business_summary,
    _gemini_text,
    answer_business_question,
    generate_business_review,
)
from .models import AIRecommendation


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

    @override_settings(GEMINI_API_KEY="configured-on-server", GEMINI_MODEL="gemini-test")
    @patch("ai_engine.gemini.time.sleep")
    @patch("google.genai.Client")
    def test_temporary_service_unavailable_is_retried(self, mocked_client, mocked_sleep):
        mocked_client.return_value.models.generate_content.side_effect = [
            APIError(503, {"error": {"message": "Service unavailable"}}),
            MagicMock(text="Recovered response"),
        ]

        answer = _gemini_text("test prompt")

        self.assertEqual(answer, "Recovered response")
        self.assertEqual(
            mocked_client.return_value.models.generate_content.call_count,
            2,
        )
        mocked_sleep.assert_called_once_with(0.5)
        mocked_client.return_value.close.assert_called_once_with()

    @override_settings(GEMINI_API_KEY="configured-on-server")
    @patch("ai_engine.gemini.time.sleep")
    @patch("google.genai.Client")
    def test_persistent_service_unavailable_returns_clear_error(
        self, mocked_client, mocked_sleep
    ):
        mocked_client.return_value.models.generate_content.side_effect = APIError(
            503, {"error": {"message": "Service unavailable"}}
        )

        with self.assertRaisesRegex(GeminiRequestError, "temporarily unavailable \\(HTTP 503\\)"):
            _gemini_text("test prompt")

        self.assertEqual(
            mocked_client.return_value.models.generate_content.call_count,
            3,
        )
        self.assertEqual(mocked_sleep.call_count, 2)
        mocked_client.return_value.close.assert_called_once_with()

    @override_settings(GEMINI_API_KEY="configured-on-server", GEMINI_MODEL="retired-model")
    @patch("google.genai.Client")
    def test_unavailable_model_falls_back_to_an_accessible_text_model(self, mocked_client):
        mocked_client.return_value.models.generate_content.side_effect = [
            APIError(404, {"error": {"message": "Model not found"}}),
            MagicMock(text="Review your sales and inventory trends."),
        ]
        mocked_client.return_value.models.list.return_value = [
            SimpleNamespace(
                name="models/gemini-2.5-flash",
                supported_actions=["generateContent"],
            ),
            SimpleNamespace(
                name="models/gemini-2.5-flash-image",
                supported_actions=["generateContent"],
            ),
        ]

        answer = _gemini_text("test prompt")

        self.assertEqual(answer, "Review your sales and inventory trends.")
        calls = mocked_client.return_value.models.generate_content.call_args_list
        self.assertEqual(calls[0].kwargs["model"], "retired-model")
        self.assertEqual(calls[1].kwargs["model"], "gemini-2.5-flash")
        mocked_client.return_value.models.list.assert_called_once_with(
            config={"page_size": 100}
        )
        mocked_client.return_value.close.assert_called_once_with()

    @override_settings(GEMINI_API_KEY="configured-on-server", GEMINI_MODEL="retired-model")
    @patch("google.genai.Client")
    def test_unavailable_model_without_accessible_fallback_has_setup_guidance(
        self, mocked_client
    ):
        mocked_client.return_value.models.generate_content.side_effect = APIError(
            404, {"error": {"message": "Model not found"}}
        )
        mocked_client.return_value.models.list.return_value = [
            SimpleNamespace(
                name="models/gemini-2.5-flash-image",
                supported_actions=["generateContent"],
            )
        ]

        with self.assertRaisesRegex(
            GeminiRequestError, "no accessible text-generation model was found"
        ):
            _gemini_text("test prompt")

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

    @override_settings(GEMINI_API_KEY="configured-on-server")
    @patch("ai_engine.gemini._gemini_text", return_value="Start with regular one-to-ones.")
    def test_assistant_gives_general_management_advice_outside_app_metrics(self, mocked_gemini):
        answer = answer_business_question(self.business, "How can I motivate my employees?")

        self.assertEqual(answer, "Start with regular one-to-ones.")
        prompt = mocked_gemini.call_args.args[0]
        self.assertIn("even when the app's metrics do not cover the subject", prompt)
        self.assertIn("still provide useful general steps", prompt)
        self.assertIn("How can I motivate my employees?", prompt)


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
    def test_assistant_page_is_separate_and_does_not_expose_provider_names(self):
        response = self.client.get(reverse("ai_engine:assistant"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ask your business assistant")
        self.assertContains(response, "Compare my sales")
        self.assertContains(response, "Check stock risks")
        self.assertContains(response, 'data-ai-composer')
        self.assertContains(response, "css/ai-assistant.css")
        self.assertContains(response, "js/ai-assistant.js")
        self.assertNotContains(response, "Gemini")
        self.assertNotContains(response, "gemini-")

    def test_insights_page_does_not_contain_the_assistant(self):
        response = self.client.get(reverse("ai_engine:home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-ai-composer")
        self.assertNotContains(response, "Ask your business assistant")
        self.assertNotContains(response, "Gemini")
        self.assertNotContains(response, "gemini-")

    @override_settings(GEMINI_API_KEY="configured-on-server")
    @patch("ai_engine.views.answer_business_question", return_value="Sales are steady.")
    def test_assistant_answer_is_only_in_the_current_uncached_response(self, mocked_answer):
        response = self.client.post(
            reverse("ai_engine:assistant"),
            {"question": "How are my sales?"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "How are my sales?")
        self.assertContains(response, "Sales are steady.")
        self.assertIn("no-store", response["Cache-Control"])
        mocked_answer.assert_called_once_with(self.business, "How are my sales?")

        next_response = self.client.get(reverse("ai_engine:assistant"))

        self.assertEqual(next_response.status_code, 200)
        self.assertNotContains(next_response, "How are my sales?")
        self.assertNotContains(next_response, "Sales are steady.")

    @override_settings(GEMINI_API_KEY="configured-on-server")
    @patch(
        "ai_engine.views.answer_business_question",
        side_effect=GeminiRequestError(
            "The assistant is temporarily unavailable (HTTP 503). Please try again in a moment."
        ),
    )
    def test_assistant_service_errors_are_vendor_neutral(self, mocked_answer):
        response = self.client.post(
            reverse("ai_engine:assistant"),
            {"question": "How are my sales?"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "temporarily unavailable (HTTP 503)")
        self.assertNotContains(response, "Gemini")
        self.assertNotContains(response, "gemini-")
