from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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


class HardwarePointOfSaleTests(TestCase):
	def setUp(self):
		self.business = Business.objects.create(
			name='Northside Hardware',
			business_type='HARDWARE',
			email='hardware@example.com',
			phone_number='0700000000',
		)
		self.user = User.objects.create_user(
			email='hardware-owner@example.com',
			password='test-password',
			first_name='Hardware',
			role='OWNER',
			business=self.business,
		)
		self.product = Product.objects.create(
			business=self.business,
			name='Galvanized roofing nails',
			sku='NAIL-001',
			selling_price=120,
			current_stock=8,
			created_by=self.user,
		)
		self.client.force_login(self.user)

	def test_hardware_pos_renders_live_catalog_and_cart(self):
		response = self.client.get(reverse('sales:create'))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'sales/entries/hardware.html')
		self.assertContains(response, 'Galvanized roofing nails')
		self.assertContains(response, '8 available')
		self.assertContains(response, 'Your cart')
		self.assertContains(response, 'Complete sale')
		self.assertContains(response, 'data-hardware-live="checkout"')
		self.assertContains(response, 'id="hardwareCartLineTemplate"')
		content = response.content.decode()
		self.assertLess(
			content.index('id="hardwareCatalogTitle"'),
			content.index('id="hardwareCartCount"'),
		)

	def test_hardware_invoice_has_a_distinct_entry_page(self):
		response = self.client.get(reverse('sales:create'), {'mode': 'invoice'})

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'sales/entries/hardware_invoice.html')
		self.assertContains(response, 'Create an invoice')
		self.assertContains(response, 'Invoice items')
		self.assertContains(response, 'Create invoice')
		self.assertNotContains(response, 'id="hardwareCatalogTitle"')
		self.assertNotContains(response, 'id="hardwareProductGrid"')

	def test_hardware_invoice_creates_invoice_record_and_reduces_stock(self):
		response = self.client.post(reverse('sales:create'), {
			'mode': 'invoice',
			'customer': '',
			'customer_name': 'Walk-in Customer',
			'customer_phone': '',
			'customer_email': '',
			'payment_method': 'CASH',
			'discount': '20',
			'transaction_code': '',
			'notes': 'Invoice for counter pickup',
			'delivery_address': '',
			'delivery_date': '',
			'sale_items-TOTAL_FORMS': '1',
			'sale_items-INITIAL_FORMS': '0',
			'sale_items-MIN_NUM_FORMS': '1',
			'sale_items-MAX_NUM_FORMS': '1000',
			'sale_items-0-product': self.product.name,
			'sale_items-0-quantity': '2',
			'sale_items-0-unit_price': '120',
		})

		sale = Sale.objects.get(business=self.business)
		self.assertRedirects(response, reverse('sales:detail', kwargs={'sale_id': sale.id}))
		self.assertEqual(sale.total, Decimal('220.00'))
		self.assertEqual(sale.notes, 'Invoice for counter pickup')
		self.product.refresh_from_db()
		self.assertEqual(self.product.current_stock, 6)

	def test_hardware_pos_checkout_records_sale_and_reduces_stock(self):
		response = self.client.post(reverse('sales:create'), {
			'customer': '',
			'customer_name': 'Walk-in Customer',
			'customer_phone': '',
			'customer_email': '',
			'payment_method': 'CASH',
			'discount': '0',
			'transaction_code': '',
			'notes': '',
			'delivery_address': '',
			'delivery_date': '',
			'sale_items-TOTAL_FORMS': '1',
			'sale_items-INITIAL_FORMS': '0',
			'sale_items-MIN_NUM_FORMS': '1',
			'sale_items-MAX_NUM_FORMS': '1000',
			'sale_items-0-product': self.product.name,
			'sale_items-0-quantity': '2',
			'sale_items-0-unit_price': '120',
		})

		sale = Sale.objects.get(business=self.business)
		self.assertRedirects(response, reverse('sales:detail', kwargs={'sale_id': sale.id}))
		self.product.refresh_from_db()
		self.assertEqual(sale.total, Decimal('240.00'))
		self.assertEqual(self.product.current_stock, 6)

	def test_hardware_pos_rejects_quantities_above_current_stock(self):
		response = self.client.post(reverse('sales:create'), {
			'customer': '',
			'customer_name': 'Walk-in Customer',
			'customer_phone': '',
			'customer_email': '',
			'payment_method': 'CASH',
			'discount': '0',
			'transaction_code': '',
			'notes': '',
			'delivery_address': '',
			'delivery_date': '',
			'sale_items-TOTAL_FORMS': '1',
			'sale_items-INITIAL_FORMS': '0',
			'sale_items-MIN_NUM_FORMS': '1',
			'sale_items-MAX_NUM_FORMS': '1000',
			'sale_items-0-product': self.product.name,
			'sale_items-0-quantity': '9',
			'sale_items-0-unit_price': '120',
		})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Sale.objects.filter(business=self.business).count(), 0)
		self.product.refresh_from_db()
		self.assertEqual(self.product.current_stock, 8)
		self.assertContains(response, 'Only 8 unit(s) remain; 9 were requested across this cart.')

	def test_hardware_pos_rejects_discount_above_the_cart_subtotal(self):
		response = self.client.post(reverse('sales:create'), {
			'customer': '',
			'customer_name': 'Walk-in Customer',
			'customer_phone': '',
			'customer_email': '',
			'payment_method': 'CASH',
			'discount': '121',
			'transaction_code': '',
			'notes': '',
			'delivery_address': '',
			'delivery_date': '',
			'sale_items-TOTAL_FORMS': '1',
			'sale_items-INITIAL_FORMS': '0',
			'sale_items-MIN_NUM_FORMS': '1',
			'sale_items-MAX_NUM_FORMS': '1000',
			'sale_items-0-product': self.product.name,
			'sale_items-0-quantity': '1',
			'sale_items-0-unit_price': '120',
		})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(Sale.objects.filter(business=self.business).count(), 0)
		self.assertContains(response, 'Discount cannot exceed the sale subtotal.')

	def test_hardware_deliveries_page_only_shows_sales_with_delivery_details(self):
		Sale.objects.create(
			business=self.business,
			sale_number='HARDWARE-DELIVERY',
			delivery_address='14 Market Road',
			created_by=self.user,
		)
		Sale.objects.create(
			business=self.business,
			sale_number='HARDWARE-COUNTER',
			created_by=self.user,
		)

		response = self.client.get(reverse('sales:list'), {'delivery': '1'})

		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['title'], 'Deliveries')
		self.assertRegex(response.content.decode(), r'(?s)<h1[^>]*>.*?Deliveries.*?</h1>')
		self.assertEqual(response.context['page_obj'].paginator.count, 1)
		self.assertEqual(response.context['page_obj'][0].sale_number, 'HARDWARE-DELIVERY')


class HardwareQuotationFlowTests(TestCase):
	def setUp(self):
		self.business = Business.objects.create(
			name='Northside Hardware',
			business_type='HARDWARE',
			email='hardware@example.com',
			phone_number='0700000000',
		)
		self.user = User.objects.create_user(
			email='hardware-owner@example.com',
			password='test-password',
			first_name='Hardware',
			role='OWNER',
			business=self.business,
		)
		self.product = Product.objects.create(
			business=self.business,
			name='Cement 32.5N',
			sku='CEM-325',
			unit='BAG',
			selling_price=750,
			current_stock=12,
			created_by=self.user,
		)
		self.customer = Customer.objects.create(
			business=self.business,
			name='BuildRight Contractors',
			phone='0712345678',
			email='buyer@example.com',
		)
		self.client.force_login(self.user)

	def quotation_payload(self, **overrides):
		payload = {
			'customer': str(self.customer.id),
			'customer_name': 'BuildRight Contractors',
			'customer_phone': self.customer.phone,
			'customer_email': self.customer.email,
			'valid_until': '',
			'discount': '100',
			'notes': 'Deliver to site',
			'items-TOTAL_FORMS': '1',
			'items-INITIAL_FORMS': '0',
			'items-MIN_NUM_FORMS': '1',
			'items-MAX_NUM_FORMS': '100',
			'items-0-product': str(self.product.id),
			'items-0-quantity': '4',
			'items-0-unit_price': '700',
		}
		payload.update(overrides)
		return payload

	def test_project_pipeline_is_shown_before_new_quotation_form(self):
		response = self.client.get(reverse('sales:quotations'))

		self.assertEqual(response.status_code, 200)
		content = response.content.decode()
		self.assertLess(
			content.index('Project pipeline'),
			content.index('id="new-quotation"'),
		)

	def test_quote_creation_snapshots_lines_and_calculates_discounted_total(self):
		response = self.client.post(
			reverse('sales:quotations'),
			self.quotation_payload(),
		)

		from .models import HardwareQuotation
		quotation = HardwareQuotation.objects.get(business=self.business)
		item = quotation.items.get()
		self.assertRedirects(
			response,
			reverse('sales:quotation_detail', kwargs={'quotation_id': quotation.id}),
		)
		self.assertEqual(quotation.subtotal, Decimal('2800.00'))
		self.assertEqual(quotation.discount, Decimal('100.00'))
		self.assertEqual(quotation.total, Decimal('2700.00'))
		self.assertEqual(item.product_name, self.product.name)
		self.assertEqual(item.product_sku, self.product.sku)
		self.assertEqual(item.line_total, Decimal('2800.00'))
		self.product.refresh_from_db()
		self.assertEqual(self.product.current_stock, 12)

	def test_quote_form_rejects_foreign_business_products(self):
		other_business = Business.objects.create(
			name='Other Hardware',
			business_type='HARDWARE',
			email='other@example.com',
			phone_number='0700000001',
		)
		other_owner = User.objects.create_user(
			email='other-owner@example.com',
			password='test-password',
			role='OWNER',
			business=other_business,
		)
		foreign_product = Product.objects.create(
			business=other_business,
			name='Foreign product',
			sku='OTHER-001',
			selling_price=10,
			current_stock=5,
			created_by=other_owner,
		)

		response = self.client.post(
			reverse('sales:quotations'),
			self.quotation_payload(**{'items-0-product': str(foreign_product.id)}),
		)

		self.assertEqual(response.status_code, 200)
		self.assertFalse(response.context['item_formset'].is_valid())
		self.assertFalse(self.business.hardware_quotations.exists())

	def test_discount_cannot_exceed_quote_subtotal(self):
		response = self.client.post(
			reverse('sales:quotations'),
			self.quotation_payload(discount='2801'),
		)

		self.assertEqual(response.status_code, 200)
		self.assertFalse(self.business.hardware_quotations.exists())
		self.assertContains(response, 'Discount cannot exceed the quotation subtotal.')

	def test_expired_quotation_cannot_be_accepted_or_converted(self):
		from .models import HardwareQuotation
		quotation = HardwareQuotation.objects.create(
			business=self.business,
			customer=self.customer,
			customer_name=self.customer.name,
			status='SENT',
			valid_until=timezone.localdate() - timedelta(days=1),
			created_by=self.user,
		)

		response = self.client.post(
			reverse('sales:quotation_action', kwargs={'quotation_id': quotation.id}),
			{'action': 'accept'},
		)
		self.assertRedirects(
			response,
			reverse('sales:quotation_detail', kwargs={'quotation_id': quotation.id}),
		)
		quotation.refresh_from_db()
		self.assertEqual(quotation.status, 'SENT')

		response = self.client.get(
			reverse('sales:quotation_convert', kwargs={'quotation_id': quotation.id})
		)
		self.assertRedirects(
			response,
			reverse('sales:quotation_detail', kwargs={'quotation_id': quotation.id}),
		)
		self.assertEqual(self.business.sales.count(), 0)

	def test_quotation_transitions_to_accepted_and_converts_to_sale_once(self):
		from .models import HardwareQuotation
		quotation = HardwareQuotation.objects.create(
			business=self.business,
			customer=self.customer,
			customer_name=self.customer.name,
			customer_phone=self.customer.phone,
			customer_email=self.customer.email,
			status='SENT',
			subtotal=Decimal('2800.00'),
			discount=Decimal('100.00'),
			total=Decimal('2700.00'),
			created_by=self.user,
		)
		quotation.items.create(
			product=self.product,
			product_name=self.product.name,
			product_sku=self.product.sku,
			unit=self.product.unit,
			quantity=4,
			unit_price=Decimal('700.00'),
		)
		detail_url = reverse('sales:quotation_detail', kwargs={'quotation_id': quotation.id})
		response = self.client.post(
			reverse('sales:quotation_action', kwargs={'quotation_id': quotation.id}),
			{'action': 'accept'},
		)
		self.assertRedirects(response, detail_url)
		quotation.refresh_from_db()
		self.assertEqual(quotation.status, 'ACCEPTED')

		convert_response = self.client.get(
			reverse('sales:quotation_convert', kwargs={'quotation_id': quotation.id})
		)
		self.assertRedirects(
			convert_response,
			f"{reverse('sales:create')}?quotation={quotation.id}",
		)
		pos_response = self.client.get(
			reverse('sales:create'),
			{'quotation': str(quotation.id)},
		)
		self.assertEqual(pos_response.status_code, 200)
		self.assertContains(pos_response, 'name="quotation_id"')
		self.assertContains(pos_response, 'value="700.00"')

		edited_quote_response = self.client.post(
			reverse('sales:create'),
			{
				'quotation_id': str(quotation.id),
				'customer': str(self.customer.id),
				'customer_name': self.customer.name,
				'customer_phone': self.customer.phone,
				'customer_email': self.customer.email,
				'payment_method': 'CASH',
				'discount': '100',
				'transaction_code': '',
				'notes': 'Deliver to site',
				'delivery_address': '',
				'delivery_date': '',
				'sale_items-TOTAL_FORMS': '1',
				'sale_items-INITIAL_FORMS': '0',
				'sale_items-MIN_NUM_FORMS': '1',
				'sale_items-MAX_NUM_FORMS': '1000',
				'sale_items-0-product': self.product.name,
				'sale_items-0-quantity': '4',
				'sale_items-0-unit_price': '701',
			},
		)
		self.assertEqual(edited_quote_response.status_code, 200)
		self.assertContains(edited_quote_response, 'Checkout details must match the accepted quotation.')
		self.assertFalse(self.business.sales.exists())
		quotation.refresh_from_db()
		self.assertEqual(quotation.status, 'ACCEPTED')

		sale_response = self.client.post(
			reverse('sales:create'),
			{
				'quotation_id': str(quotation.id),
				'customer': str(self.customer.id),
				'customer_name': self.customer.name,
				'customer_phone': self.customer.phone,
				'customer_email': self.customer.email,
				'payment_method': 'CASH',
				'discount': '100',
				'transaction_code': '',
				'notes': 'Deliver to site',
				'delivery_address': '',
				'delivery_date': '',
				'sale_items-TOTAL_FORMS': '1',
				'sale_items-INITIAL_FORMS': '0',
				'sale_items-MIN_NUM_FORMS': '1',
				'sale_items-MAX_NUM_FORMS': '1000',
				'sale_items-0-product': self.product.name,
				'sale_items-0-quantity': '4',
				'sale_items-0-unit_price': '700',
			},
		)

		from .models import Sale
		sale = Sale.objects.get(business=self.business)
		self.assertRedirects(sale_response, reverse('sales:detail', kwargs={'sale_id': sale.id}))
		quotation.refresh_from_db()
		self.product.refresh_from_db()
		self.assertEqual(quotation.status, 'CONVERTED')
		self.assertEqual(quotation.converted_sale_id, sale.id)
		self.assertEqual(sale.total, Decimal('2700.00'))
		self.assertEqual(self.product.current_stock, 8)


class RestaurantOrderFlowTests(TestCase):
	def setUp(self):
		self.business = Business.objects.create(
			name='Live Restaurant',
			business_type='RESTAURANT',
			email='restaurant@example.com',
			phone_number='0700000000',
		)
		self.user = User.objects.create_user(
			email='restaurant-owner@example.com',
			password='test-password',
			first_name='Restaurant',
			last_name='Owner',
			role='OWNER',
			business=self.business,
		)
		self.product = Product.objects.create(
			business=self.business,
			name='House Burger',
			sku='BURGER-001',
			selling_price=850,
			current_stock=10,
			created_by=self.user,
		)
		self.client.force_login(self.user)

	def test_order_entry_renders_restaurant_menu_and_three_column_workflow(self):
		for index in range(25):
			Product.objects.create(
				business=self.business,
				name=f'Menu item {index:02d}',
				sku=f'MENU-{index:02d}',
				selling_price=100 + index,
				current_stock=10,
				created_by=self.user,
			)

		response = self.client.get(reverse('sales:create'))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, 'sales/entries/restaurant.html')
		self.assertContains(response, 'Menu')
		self.assertContains(response, 'Current order')
		self.assertContains(response, 'Checkout')
		self.assertContains(response, 'Menu item 24')

	def test_restaurant_order_saves_order_and_table_metadata(self):
		response = self.client.post(reverse('sales:create'), {
			'customer': '',
			'customer_name': 'Walk-in customer',
			'customer_phone': '',
			'customer_email': '',
			'payment_method': 'CASH',
			'discount': '0',
			'transaction_code': '',
			'served_by': str(self.user.id),
			'order_type': 'DINE_IN',
			'table_reference': 'Table 4',
			'notes': 'No onions',
			'delivery_address': '',
			'delivery_date': '',
			'sale_items-TOTAL_FORMS': '1',
			'sale_items-INITIAL_FORMS': '0',
			'sale_items-MIN_NUM_FORMS': '1',
			'sale_items-MAX_NUM_FORMS': '1000',
			'sale_items-0-product': self.product.name,
			'sale_items-0-quantity': '2',
			'sale_items-0-unit_price': '850',
			'sale_items-0-DELETE': '',
		})

		sale = Sale.objects.get(business=self.business)

		self.assertRedirects(response, reverse('sales:detail', kwargs={'sale_id': sale.id}))
		self.assertEqual(sale.metadata['order_type'], 'DINE_IN')
		self.assertEqual(sale.metadata['table_reference'], 'Table 4')
		self.assertEqual(sale.metadata['served_by']['id'], str(self.user.id))
		self.assertEqual(sale.sale_items.get().quantity, 2)
		self.assertEqual(sale.total, Decimal('1700'))


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
