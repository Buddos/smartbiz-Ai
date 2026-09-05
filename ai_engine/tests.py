from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from businesses.models import Business
from products.models import Product
from sales.models import Sale, SaleItem

from .models import AIInsight, AIRecommendation, FeatureSnapshot
from .services import run_intelligence_pipeline


@override_settings(AI_ENGINE_EVENT_PIPELINE=False)
class IntelligencePipelineTests(TestCase):
	def setUp(self):
		self.business = Business.objects.create(
			name="Pipeline Test Shop",
			email="pipeline@example.com",
			phone_number="0700000000",
		)
		self.product = Product.objects.create(
			business=self.business,
			name="Test Sugar",
			sku="TEST-SUGAR",
			purchase_price=Decimal("80.00"),
			selling_price=Decimal("100.00"),
			current_stock=2,
			reorder_level=5,
		)

	def add_sale(self, sale_date, quantity=3):
		sale = Sale.objects.create(
			business=self.business,
			sale_number=f"TEST-{Sale.objects.count() + 1}",
			sale_date=sale_date,
			subtotal=Decimal("0"),
			total=Decimal("0"),
		)
		SaleItem.objects.create(
			sale=sale,
			product=self.product,
			quantity=quantity,
			unit_price=Decimal("100.00"),
			cost_price=Decimal("80.00"),
			tax_rate=Decimal("0.00"),
			discount=Decimal("0.00"),
		)
		sale.recalculate()

	def test_pipeline_creates_features_ranked_insights_and_recommendations(self):
		today = timezone.now()
		self.add_sale(today - timedelta(days=2), quantity=5)
		self.add_sale(today - timedelta(days=40), quantity=1)

		created = run_intelligence_pipeline(self.business, as_of=today.date())

		self.assertTrue(created)
		self.assertTrue(FeatureSnapshot.objects.filter(business=self.business).exists())
		self.assertTrue(AIRecommendation.objects.filter(business=self.business).exists())
		self.assertTrue(all(0 <= insight.score <= 1 for insight in created))
		self.assertTrue(all(insight.source_model == "rules.v1" for insight in created))

	def test_pipeline_deduplicates_active_insights_for_seven_days(self):
		today = timezone.now()
		self.add_sale(today - timedelta(days=2), quantity=5)

		first = run_intelligence_pipeline(self.business, as_of=today.date())
		second = run_intelligence_pipeline(self.business, as_of=today.date())

		self.assertTrue(first)
		self.assertEqual(second, [])
		self.assertEqual(AIInsight.objects.filter(business=self.business).count(), len(first))
