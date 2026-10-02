from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from barber.models import Appointment, BarberService, Chair
from businesses.models import Business, BusinessSettings
from customers.models import Customer
from products.models import Category, Product

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


class ElectronicsSaleCheckoutTests(TestCase):
	def setUp(self):
		self.business = Business.objects.create(
			name='Live Electronics',
			business_type='ELECTRONICS',
			email='shop@example.com',
			phone_number='0700000000',
		)
		self.user = User.objects.create_user(
			email='cashier@example.com',
			password='test-password',
			first_name='Shop',
			last_name='Cashier',
			role='OWNER',
			business=self.business,
		)
		self.category = Category.objects.create(business=self.business, name='Phones')
		self.product = Product.objects.create(
			business=self.business,
			name='Galaxy A15',
			sku='GAL-A15',
			category=self.category,
			selling_price=22500,
			current_stock=3,
			reorder_level=2,
			created_by=self.user,
		)
		self.client.force_login(self.user)

	def _sale_data(self, *, payment_method='CASH', item_count=1, quantity=1):
		data = {
			'customer': '',
			'customer_name': 'Walk-in Customer',
			'customer_phone': '',
			'customer_email': '',
			'payment_method': payment_method,
			'discount': '0',
			'transaction_code': '',
			'served_by': '',
			'serial_number': '',
			'warranty_period': '',
			'notes': '',
			'delivery_address': '',
			'delivery_date': '',
			'sale_items-TOTAL_FORMS': str(item_count),
			'sale_items-INITIAL_FORMS': '0',
			'sale_items-MIN_NUM_FORMS': '1',
			'sale_items-MAX_NUM_FORMS': '1000',
		}
		for index in range(item_count):
			data[f'sale_items-{index}-product'] = self.product.name
			data[f'sale_items-{index}-quantity'] = str(quantity)
			data[f'sale_items-{index}-unit_price'] = str(self.product.selling_price)
		return data

	def test_electronics_checkout_displays_live_catalog_and_cashier_ui(self):
		response = self.client.get(reverse('sales:create'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Galaxy A15')
		self.assertContains(response, '3 in stock')
		self.assertContains(response, 'Phones')
		self.assertContains(response, 'Complete sale')
		self.assertContains(response, 'Assigned on completion')
		self.assertTemplateUsed(response, 'sales/entries/electronics.html')

	def test_credit_sale_requires_a_saved_customer(self):
		response = self.client.post(
			reverse('sales:create'),
			self._sale_data(payment_method='CREDIT'),
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Sale.objects.filter(business=self.business).count(), 0)
		self.assertContains(response, 'Select a saved customer for a credit sale.')

	def test_duplicate_cart_lines_cannot_oversell_stock(self):
		response = self.client.post(
			reverse('sales:create'),
			self._sale_data(item_count=2, quantity=2),
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Sale.objects.filter(business=self.business).count(), 0)
		self.product.refresh_from_db()
		self.assertEqual(self.product.current_stock, 3)
		self.assertContains(response, 'Only 3 unit(s) remain')

	def test_discount_cannot_exceed_cart_subtotal(self):
		data = self._sale_data()
		data['discount'] = str(self.product.selling_price + 1)

		response = self.client.post(reverse('sales:create'), data)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Sale.objects.filter(business=self.business).count(), 0)
		self.assertContains(response, 'Discount cannot exceed the sale subtotal.')

	def test_inclusive_tax_is_shown_in_summary_without_being_added_twice(self):
		BusinessSettings.objects.create(
			business=self.business,
			tax_enabled=True,
			tax_rate='16.00',
			tax_inclusive=True,
		)

		response = self.client.post(reverse('sales:create'), self._sale_data())

		sale = Sale.objects.get(business=self.business)
		item = sale.sale_items.get()
		self.assertRedirects(response, reverse('sales:detail', kwargs={'sale_id': sale.id}))
		self.assertEqual(item.tax_rate, 16)
		self.assertEqual(item.tax_amount, Decimal('3103.45'))
		self.assertEqual(sale.tax, Decimal('3103.45'))
		self.assertEqual(sale.total, 22500)
		self.assertEqual(sale.amount_paid, 22500)

	def test_exclusive_tax_is_added_to_electronics_sale_total(self):
		BusinessSettings.objects.create(
			business=self.business,
			tax_enabled=True,
			tax_rate='16.00',
			tax_inclusive=False,
		)

		response = self.client.post(reverse('sales:create'), self._sale_data())

		sale = Sale.objects.get(business=self.business)
		self.assertRedirects(response, reverse('sales:detail', kwargs={'sale_id': sale.id}))
		self.assertEqual(sale.tax, 3600)
		self.assertEqual(sale.total, 26100)


class BarberQuickSaleTests(TestCase):
	def setUp(self):
		self.business = Business.objects.create(
			name='Quick Cut Barbershop',
			business_type='BARBER',
			email='shop@example.com',
			phone_number='0700000000',
		)
		self.barber = User.objects.create_user(
			email='barber@example.com',
			password='test-password',
			first_name='Marcus',
			last_name='Barber',
			role='BARBER',
			business=self.business,
		)
		self.chair = Chair.objects.create(
			business=self.business,
			label='Chair 1',
			barber=self.barber,
		)
		self.service = BarberService.objects.create(
			business=self.business,
			name='Haircut',
			price=350,
		)
		self.product = Product.objects.create(
			business=self.business,
			name='Haircut',
			sku='CUT-001',
			selling_price=350,
			created_by=self.barber,
		)
		self.appointment = Appointment.objects.create(
			business=self.business,
			client_name='Marcus',
			service=self.service,
			barber=self.barber,
			chair=self.chair,
			status='IN_CHAIR',
		)
		self.client.force_login(self.barber)

	def _sale_data(self, appointment_id):
		return {
			'appointment_id': str(appointment_id),
			'customer': '',
			'customer_name': 'Marcus',
			'customer_phone': '',
			'customer_email': '',
			'payment_method': 'M-PESA',
			'discount': '0',
			'transaction_code': '',
			'served_by': str(self.barber.id),
			'notes': '',
			'delivery_address': '',
			'delivery_date': '',
			'sale_items-TOTAL_FORMS': '1',
			'sale_items-INITIAL_FORMS': '0',
			'sale_items-MIN_NUM_FORMS': '1',
			'sale_items-MAX_NUM_FORMS': '1000',
			'sale_items-0-product': self.product.name,
			'sale_items-0-quantity': '1',
			'sale_items-0-unit_price': '350',
		}

	def test_checkout_prefills_active_appointment_and_completes_sale(self):
		response = self.client.get(reverse('sales:create'))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Marcus')
		self.assertContains(response, str(self.appointment.id))
		self.assertContains(response, 'name="sale_items-TOTAL_FORMS" value="1"')
		self.assertContains(response, '+ Add another item')
		self.assertNotContains(response, 'SMS not configured')

		response = self.client.post(reverse('sales:create'), self._sale_data(self.appointment.id))

		sale = Sale.objects.get(business=self.business)
		self.appointment.refresh_from_db()
		self.assertRedirects(response, reverse('sales:detail', kwargs={'sale_id': sale.id}))
		self.assertEqual(sale.payment_method, 'M-PESA')
		self.assertEqual(sale.payment_status, 'PAID')
		self.assertEqual(sale.amount_paid, sale.total)
		self.assertEqual(sale.barber, self.barber)
		self.assertEqual(self.appointment.status, 'DONE')
		self.assertEqual(self.appointment.sale, sale)
		self.assertIsNotNone(self.appointment.completed_at)

		floor_response = self.client.get(reverse('barber:live_floor'))
		self.assertEqual(floor_response.json()['metrics']['occupied'], 0)
		self.assertEqual(floor_response.json()['metrics']['cuts'], 1)

	def test_barber_cannot_close_another_barbers_active_appointment(self):
		other_barber = User.objects.create_user(
			email='other@example.com',
			password='test-password',
			first_name='Other',
			last_name='Barber',
			role='BARBER',
			business=self.business,
		)
		self.client.force_login(other_barber)

		response = self.client.post(reverse('sales:create'), self._sale_data(self.appointment.id))

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Sale.objects.filter(business=self.business).count(), 0)
		self.appointment.refresh_from_db()
		self.assertEqual(self.appointment.status, 'IN_CHAIR')
		self.assertIsNone(self.appointment.sale)

	def test_unused_added_item_is_deleted_from_sale(self):
		data = self._sale_data(self.appointment.id)
		data.update({
			'sale_items-TOTAL_FORMS': '2',
			'sale_items-1-product': '',
			'sale_items-1-quantity': '1',
			'sale_items-1-unit_price': '',
			'sale_items-1-DELETE': 'on',
		})

		response = self.client.post(reverse('sales:create'), data)

		sale = Sale.objects.get(business=self.business)
		self.assertRedirects(response, reverse('sales:detail', kwargs={'sale_id': sale.id}))
		self.assertEqual(sale.sale_items.count(), 1)
