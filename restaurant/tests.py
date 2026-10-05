from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from businesses.models import Business
from inventory.models import InventoryTransaction
from products.models import Product
from sales.models import Payment, Sale, SaleItem

from .models import (
    KitchenTicket,
    RestaurantCashShift,
    RestaurantPurchaseOrder,
    RestaurantPurchaseOrderLine,
    RestaurantRecipe,
    RestaurantRecipeIngredient,
    RestaurantReservation,
    RestaurantSupplier,
    RestaurantTable,
)


class RestaurantOperationsTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Live Restaurant",
            business_type="RESTAURANT",
            email="live-restaurant@example.com",
            phone_number="0700000000",
        )
        self.owner = User.objects.create_user(
            email="live-owner@example.com",
            password="safe-password-123",
            role="OWNER",
            business=self.business,
        )
        self.client.force_login(self.owner)

    def make_product(self, name, sku, *, cost="50.00", price="200.00"):
        return Product.objects.create(
            business=self.business,
            name=name,
            sku=sku,
            purchase_price=Decimal(cost),
            selling_price=Decimal(price),
        )

    def test_operations_pages_render_empty_states_from_saved_records(self):
        for route_name in (
            "restaurant:tables",
            "restaurant:reservations",
            "restaurant:kitchen",
            "restaurant:menu",
            "restaurant:ingredients",
            "restaurant:recipes",
            "restaurant:suppliers",
            "restaurant:cash_drawer",
            "restaurant:food_cost",
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Live restaurant operations")
                self.assertContains(response, "restaurantSidebar")
                self.assertContains(response, "dashboard-readable")

    def test_table_status_actions_are_persisted_and_tenant_scoped(self):
        table = RestaurantTable.objects.create(
            business=self.business,
            number="T1",
            seats=4,
        )
        response = self.client.post(
            reverse("restaurant:table_action", args=[table.pk, "seat"])
        )
        self.assertRedirects(response, reverse("restaurant:tables"))
        table.refresh_from_db()
        self.assertEqual(table.status, "OCCUPIED")
        self.assertIsNotNone(table.seated_at)

        other_business = Business.objects.create(
            name="Different Restaurant",
            business_type="RESTAURANT",
            email="different@example.com",
            phone_number="0711111111",
        )
        other_table = RestaurantTable.objects.create(business=other_business, number="T1")
        response = self.client.post(
            reverse("restaurant:table_action", args=[other_table.pk, "clear"])
        )
        self.assertEqual(response.status_code, 404)
        other_table.refresh_from_db()
        self.assertEqual(other_table.status, "AVAILABLE")

    def test_manager_can_save_unique_business_scoped_floor_positions(self):
        first = RestaurantTable.objects.create(
            business=self.business,
            number="L1",
            position_x=0,
            position_y=0,
        )
        second = RestaurantTable.objects.create(
            business=self.business,
            number="L2",
            position_x=1,
            position_y=0,
        )
        save_url = reverse("restaurant:table_layout_save")
        response = self.client.post(
            save_url,
            {
                "table_id": [str(first.pk), str(second.pk)],
                "position_x": ["2", "3"],
                "position_y": ["4", "4"],
            },
        )
        self.assertRedirects(response, reverse("restaurant:tables"))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.position_x, first.position_y), (2, 4))
        self.assertEqual((second.position_x, second.position_y), (3, 4))

        other_business = Business.objects.create(
            name="Foreign Layout",
            business_type="RESTAURANT",
            email="foreign-layout@example.com",
            phone_number="0733333333",
        )
        foreign_table = RestaurantTable.objects.create(
            business=other_business,
            number="F1",
        )
        response = self.client.post(
            save_url,
            {
                "table_id": [str(first.pk), str(foreign_table.pk)],
                "position_x": ["6", "6"],
                "position_y": ["6", "6"],
            },
        )
        self.assertRedirects(response, reverse("restaurant:tables"))
        first.refresh_from_db()
        self.assertEqual((first.position_x, first.position_y), (2, 4))

        response = self.client.post(
            reverse("restaurant:tables"),
            {"number": "L3", "zone": "Indoor", "seats": "2"},
        )
        self.assertRedirects(response, reverse("restaurant:tables"))
        added_table = RestaurantTable.objects.get(business=self.business, number="L3")
        self.assertEqual((added_table.position_x, added_table.position_y), (2, 0))

        response = self.client.post(
            save_url,
            {
                "table_id": [str(first.pk), str(second.pk)],
                "position_x": ["5", "5"],
                "position_y": ["5", "5"],
            },
        )
        self.assertRedirects(response, reverse("restaurant:tables"))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.position_x, first.position_y), (2, 4))
        self.assertEqual((second.position_x, second.position_y), (3, 4))

    def test_reservation_saves_and_seating_updates_its_real_table(self):
        table = RestaurantTable.objects.create(
            business=self.business,
            number="T2",
            seats=4,
        )
        start = timezone.localtime(timezone.now() + timedelta(days=1)).replace(second=0, microsecond=0)
        response = self.client.post(
            reverse("restaurant:reservations"),
            {
                "customer_name": "Alex Diner",
                "phone": "0700111222",
                "starts_at": start.strftime("%Y-%m-%dT%H:%M"),
                "party_size": 3,
                "table": str(table.pk),
                "deposit": "0.00",
                "notes": "Window seat",
            },
        )
        self.assertRedirects(response, reverse("restaurant:reservations"))
        reservation = RestaurantReservation.objects.get(business=self.business)
        self.assertEqual(reservation.customer_name, "Alex Diner")
        self.assertEqual(reservation.table, table)
        table.refresh_from_db()
        self.assertEqual(table.status, "RESERVED")

        response = self.client.post(
            reverse("restaurant:reservation_action", args=[reservation.pk, "seat"])
        )
        self.assertRedirects(response, reverse("restaurant:reservations"))
        reservation.refresh_from_db()
        table.refresh_from_db()
        self.assertEqual(reservation.status, "SEATED")
        self.assertEqual(table.status, "OCCUPIED")

    def test_kitchen_ticket_is_created_from_a_real_restaurant_sale_item(self):
        product = self.make_product("Soup", "SOUP-1")
        sale = Sale.objects.create(
            business=self.business,
            sale_number="ORDER-1",
            order_status="PROCESSING",
            metadata={"table_reference": "T4"},
        )
        SaleItem.objects.create(
            sale=sale,
            product=product,
            product_name=product.name,
            product_sku=product.sku,
            unit_price=product.selling_price,
            cost_price=product.purchase_price,
            quantity=2,
        )
        ticket = KitchenTicket.objects.get(sale=sale)
        self.assertEqual(ticket.status, "NEW")
        ticket.transition("COOKING")
        ticket.transition("READY")
        self.assertIsNotNone(ticket.ready_at)
        with self.assertRaises(ValueError):
            ticket.transition("COOKING")

    def test_menu_station_assignment_filters_real_kitchen_items(self):
        product = self.make_product("Grilled fish", "FISH-1")
        response = self.client.post(
            reverse("restaurant:menu"),
            {"product_id": str(product.pk), "station": "GRILL", "is_active": "on"},
        )
        self.assertRedirects(response, reverse("restaurant:menu"))
        product.refresh_from_db()
        self.assertEqual(product.metadata["restaurant_station"], "GRILL")
        menu_response = self.client.get(reverse("restaurant:menu"))
        self.assertContains(menu_response, "Grilled fish")

        sale = Sale.objects.create(
            business=self.business,
            sale_number="ORDER-STATION",
            order_status="PROCESSING",
        )
        SaleItem.objects.create(
            sale=sale,
            product=product,
            product_name=product.name,
            product_sku=product.sku,
            unit_price=product.selling_price,
            cost_price=product.purchase_price,
            quantity=1,
        )
        grill_response = self.client.get(reverse("restaurant:kitchen"), {"station": "GRILL"})
        fry_response = self.client.get(reverse("restaurant:kitchen"), {"station": "FRY"})
        self.assertContains(grill_response, "Grilled fish")
        self.assertNotContains(fry_response, "Grilled fish")

    def test_recipe_portion_cost_uses_saved_ingredient_price_and_quantity(self):
        menu_item = self.make_product("Stew", "STEw-1", cost="80.00", price="400.00")
        ingredient = self.make_product("Tomato", "TOM-1", cost="120.00")
        recipe = RestaurantRecipe.objects.create(menu_item=menu_item)
        RestaurantRecipeIngredient.objects.create(
            recipe=recipe,
            ingredient=ingredient,
            quantity=Decimal("0.5"),
            unit="KG",
        )
        self.assertEqual(recipe.portion_cost, Decimal("60.000"))
        self.assertEqual(recipe.margin_percent, Decimal("85.00000"))
        menu_item.refresh_from_db()
        self.assertEqual(menu_item.purchase_price, Decimal("60.000"))

        ingredient.purchase_price = Decimal("160.00")
        ingredient.save(update_fields=["purchase_price"])
        menu_item.refresh_from_db()
        self.assertEqual(menu_item.purchase_price, Decimal("80.000"))

    def test_recipe_form_saves_real_ingredient_lines_and_updates_menu_cost(self):
        menu_item = self.make_product("Bean bowl", "BEAN-1", price="300.00")
        ingredient = self.make_product("Beans", "BEANS-1", cost="80.00")
        response = self.client.post(
            reverse("restaurant:recipes"),
            {
                "menu_item": str(menu_item.pk),
                "preparation_minutes": "20",
                "yield_percent": "100",
                "waste_percent": "0",
                "method": "Cook until tender.",
                "ingredient": [str(ingredient.pk)],
                "quantity": ["0.5"],
            },
        )
        self.assertRedirects(response, reverse("restaurant:recipes"))
        recipe = RestaurantRecipe.objects.get(menu_item=menu_item)
        self.assertEqual(recipe.ingredients.count(), 1)
        menu_item.refresh_from_db()
        self.assertEqual(menu_item.purchase_price, Decimal("40.000"))

    def test_supplier_and_cash_shift_are_stored_for_this_business(self):
        supplier = RestaurantSupplier.objects.create(
            business=self.business,
            name="Fresh Produce",
            phone="0700999888",
        )
        shift = RestaurantCashShift.objects.create(
            business=self.business,
            opened_by=self.owner,
            opening_cash=Decimal("1000.00"),
        )
        sale = Sale.objects.create(business=self.business, sale_number="CASH-SALE")
        Payment.objects.create(
            sale=sale,
            business=self.business,
            payment_number="CASH-PAYMENT",
            amount=Decimal("25.00"),
            payment_method="CASH",
            payment_status="COMPLETED",
        )
        self.assertEqual(supplier.business, self.business)
        self.assertEqual(shift.expected_cash, Decimal("1025.00"))
        with self.assertRaises(IntegrityError):
            RestaurantCashShift.objects.create(
                business=self.business,
                opened_by=self.owner,
                opening_cash=Decimal("0.00"),
            )

    def test_supplier_purchase_order_receives_inventory_and_rejects_foreign_products(self):
        supplier = RestaurantSupplier.objects.create(
            business=self.business,
            name="Market Produce",
        )
        stock_item = self.make_product("Rice", "RICE-1", cost="10.00")
        order_url = reverse("restaurant:supplier_orders", args=[supplier.pk])

        other_business = Business.objects.create(
            name="Another Restaurant",
            business_type="RESTAURANT",
            email="other-restaurant@example.com",
            phone_number="0722222222",
        )
        foreign_item = Product.objects.create(
            business=other_business,
            name="Foreign flour",
            sku="FLOUR-1",
        )
        response = self.client.post(
            order_url,
            {
                "product": str(foreign_item.pk),
                "quantity": "4",
                "unit_cost": "25.00",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(RestaurantPurchaseOrder.objects.filter(business=self.business).exists())

        response = self.client.post(
            order_url,
            {
                "product": str(stock_item.pk),
                "quantity": "4",
                "unit_cost": "25.00",
            },
        )
        self.assertRedirects(response, order_url)
        order = RestaurantPurchaseOrder.objects.get(business=self.business)
        self.assertEqual(order.lines.count(), 1)

        response = self.client.post(
            reverse("restaurant:purchase_order_receive", args=[order.pk])
        )
        self.assertRedirects(response, order_url)
        order.refresh_from_db()
        stock_item.refresh_from_db()
        self.assertEqual(order.status, "RECEIVED")
        self.assertEqual(stock_item.current_stock, 4)
        self.assertEqual(stock_item.purchase_price, Decimal("25.00"))
        transaction = InventoryTransaction.objects.get(
            reference_id=str(order.pk),
            transaction_type="RECEIVED",
        )
        self.assertEqual(transaction.quantity, 4)

    def test_invalid_cash_close_amount_is_shown_without_closing_shift(self):
        shift = RestaurantCashShift.objects.create(
            business=self.business,
            opened_by=self.owner,
            opening_cash=Decimal("100.00"),
        )
        response = self.client.post(
            reverse("restaurant:cash_drawer"),
            {"action": "close", "closing_cash": "-1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ensure this value is greater than or equal to 0.")
        shift.refresh_from_db()
        self.assertIsNone(shift.closed_at)
