from types import SimpleNamespace

from django.test import TestCase

from .capabilities import (
	dashboard_capabilities_for_business,
	dashboard_profile_for_business,
	resolve_business_configuration,
	sale_template_for_business,
)


class SaleTemplateResolverTests(TestCase):
	def test_inventory_business_gets_inventory_sale_template(self):
		business = SimpleNamespace(business_type='RETAIL', enabled_capabilities=['inventory'])

		template = sale_template_for_business(business)

		self.assertEqual(template['id'], 'inventory')
		self.assertEqual(template['item_label'], 'Products')
		self.assertIn('payment', template['sections'])

	def test_capabilities_drive_sections_and_configuration_outputs(self):
		business = SimpleNamespace(
			business_type='SALON',
			enabled_capabilities=['appointments', 'customer_credit'],
		)

		configuration = resolve_business_configuration(business)

		self.assertIn('booking', configuration['sale_template']['sections'])
		self.assertIn('credit', configuration['sale_template']['sections'])
		self.assertEqual(configuration['navigation'][0]['label'], 'Sales')

	def test_unknown_capabilities_are_ignored(self):
		business = SimpleNamespace(business_type='OTHER', enabled_capabilities=['not-a-capability'])

		template = sale_template_for_business(business)

		self.assertEqual(template['id'], 'standard')
		self.assertEqual(template['capabilities'], [])

	def test_dashboard_shows_each_selected_capability(self):
		business = SimpleNamespace(
			business_type='RESTAURANT',
			enabled_capabilities=['tables', 'menu'],
		)

		cards = dashboard_capabilities_for_business(business)

		self.assertEqual([card['id'] for card in cards], ['tables', 'menu'])
		self.assertEqual(cards[0]['label'], 'Table & order management')
		self.assertEqual(cards[0]['url'], 'sales:list')

	def test_business_type_changes_sale_page_profile(self):
		restaurant = SimpleNamespace(business_type='RESTAURANT', enabled_capabilities=['tables'])
		retail = SimpleNamespace(business_type='RETAIL', enabled_capabilities=['inventory'])

		restaurant_template = sale_template_for_business(restaurant)
		retail_template = sale_template_for_business(retail)

		self.assertEqual(restaurant_template['title'], 'New Restaurant Order')
		self.assertIn('table', restaurant_template['sections'])
		self.assertEqual(retail_template['title'], 'New Retail Sale')
		self.assertNotIn('table', retail_template['sections'])

	def test_registered_business_type_gets_unique_dashboard_profile(self):
		restaurant = SimpleNamespace(business_type='RESTAURANT', enabled_capabilities=['tables'])
		electronics = SimpleNamespace(business_type='ELECTRONICS', enabled_capabilities=['inventory'])

		restaurant_profile = dashboard_profile_for_business(restaurant)
		electronics_profile = dashboard_profile_for_business(electronics)

		self.assertEqual(restaurant_profile['id'], 'restaurant')
		self.assertEqual(electronics_profile['id'], 'electronics')
		self.assertNotEqual(restaurant_profile['title'], electronics_profile['title'])

	def test_each_business_type_gets_a_unique_sale_entry_template(self):
		business_types = [
			'RETAIL', 'RESTAURANT', 'SALON', 'WHOLESALE', 'SERVICE',
			'ELECTRONICS', 'BOUTIQUE', 'HARDWARE', 'FREELANCE', 'OTHER',
		]

		templates = [
			sale_template_for_business(
				SimpleNamespace(business_type=business_type, enabled_capabilities=[])
			)['entry_template']
			for business_type in business_types
		]

		self.assertEqual(len(templates), len(set(templates)))
		self.assertTrue(all(template.startswith('sales/entries/') for template in templates))
