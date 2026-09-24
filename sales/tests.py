from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from businesses.models import Business
from products.models import Product

from .models import Sale


class SaleCreateFlowTests(TestCase):
	def test_valid_sale_saves_and_redirects_to_detail(self):
		business = Business.objects.create(
			name='Test Retail Shop',
			business_type='RETAIL',
			email='shop@example.com',
			phone_number='0700000000',
		)
		user = User.objects.create_user(
			email='owner@example.com',
			password='test-password',
			first_name='Test',
			last_name='Owner',
			role='OWNER',
			business=business,
		)
		product = Product.objects.create(
			business=business,
			name='Test Product',
			sku='TEST-001',
			selling_price=100,
			current_stock=10,
			created_by=user,
		)
		self.client.force_login(user)

		response = self.client.post(reverse('sales:create'), {
			'customer': '',
			'customer_name': 'Walk-in Customer',
			'customer_phone': '',
			'customer_email': '',
			'payment_method': 'CASH',
			'discount': '0',
			'transaction_code': 'TEST-CASH-001',
			'served_by': str(user.id),
			'notes': '',
			'delivery_address': '',
			'delivery_date': '',
			'sale_items-TOTAL_FORMS': '1',
			'sale_items-INITIAL_FORMS': '0',
			'sale_items-MIN_NUM_FORMS': '1',
			'sale_items-MAX_NUM_FORMS': '1000',
			'sale_items-0-product': product.name,
			'sale_items-0-quantity': '1',
			'sale_items-0-unit_price': '100',
		})

		sale = Sale.objects.get(business=business)

		self.assertRedirects(response, reverse('sales:detail', kwargs={'sale_id': sale.id}))
		self.assertEqual(sale.sale_items.count(), 1)
		self.assertEqual(sale.metadata['transaction_code'], 'TEST-CASH-001')
		self.assertEqual(sale.metadata['served_by']['id'], str(user.id))
		self.assertEqual(product.__class__.objects.get(pk=product.pk).current_stock, 9)
