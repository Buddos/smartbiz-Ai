from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from businesses.models import Business
from inventory.models import InventoryTransaction
from products.models import Product
from sales.models import Payment, Sale

from .models import CashDrawerSession, RetailPurchaseOrder, RetailPurchaseOrderItem, RetailSupplier
from .views import _drawer_totals
from accounts.models import User


class RetailWorkspaceTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Corner Shop",
            email="shop@example.com",
            phone_number="0712345678",
            business_type="RETAIL",
        )
        self.user = User.objects.create_user(
            email="owner@example.com",
            password="test-password",
            first_name="Shop",
            role="OWNER",
            business=self.business,
        )
        self.product = Product.objects.create(
            business=self.business,
            name="Tea",
            sku="TEA-001",
            purchase_price=Decimal("40.00"),
            selling_price=Decimal("60.00"),
            current_stock=5,
        )
        self.client.force_login(self.user)

    def test_dashboard_renders_live_empty_business_values(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["today_transactions"], 0)
        self.assertEqual(response.context["total_products"], 1)
        self.assertContains(response, "No completed product sales have been recorded today.")
        self.assertContains(response, "Corner Shop")
        self.assertContains(response, 'class="retail-sidebar"')
        self.assertContains(response, "dashboard-readable")
        self.assertLess(
            response.content.index(b"AI Assistant"),
            response.content.index(b"AI Insights"),
        )
        self.assertContains(response, 'class="retail-app-shell retail-readable"')
        self.assertContains(response, 'class="retail-account-avatar"')

    def test_retail_operation_pages_render_in_retail_shell(self):
        for route_name in ("retail:suppliers", "retail:cash_drawer", "retail:credit"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="retail-sidebar"')
                self.assertContains(response, 'class="retail-app-shell retail-readable"')

    def test_existing_business_pages_render_in_retail_shell(self):
        route_names = (
            "sales:list",
            "expenses:list",
            "products:list",
            "inventory:dashboard",
            "inventory:stock_counts",
            "customers:list",
        )
        for route_name in route_names:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="retail-sidebar"')
                self.assertContains(response, 'class="retail-app-shell retail-readable"')

    def test_supplier_purchase_order_receives_stock_once(self):
        supplier = RetailSupplier.objects.create(
            business=self.business,
            name="Local Wholesaler",
        )
        response = self.client.post(reverse("retail:suppliers"), {
            "form_type": "order",
            "order-supplier": str(supplier.pk),
            "order-expected_date": "",
            "order-notes": "",
            "items-TOTAL_FORMS": "1",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "0",
            "items-MAX_NUM_FORMS": "20",
            "items-0-product": str(self.product.pk),
            "items-0-quantity": "3",
            "items-0-unit_cost": "40.00",
        })

        self.assertRedirects(response, reverse("retail:suppliers"))
        order = RetailPurchaseOrder.objects.get()
        self.assertEqual(order.total, Decimal("120.00"))
        self.assertEqual(RetailPurchaseOrderItem.objects.filter(order=order).count(), 1)

        receive_url = reverse("retail:purchase_order_receive", args=[order.pk])
        self.client.post(receive_url)
        self.client.post(receive_url)

        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.current_stock, 8)
        self.assertEqual(order.status, "RECEIVED")
        self.assertEqual(
            InventoryTransaction.objects.filter(
                reference_id=str(order.pk),
                transaction_type="RECEIVED",
            ).count(),
            1,
        )

    def test_drawer_totals_include_cash_sales_and_cash_credit_payments(self):
        session = CashDrawerSession.objects.create(
            business=self.business,
            opened_by=self.user,
            opened_at=timezone.now() - timedelta(minutes=30),
            opening_balance=Decimal("50.00"),
        )
        Sale.objects.create(
            business=self.business,
            sale_number="CASH-001",
            payment_method="CASH",
            subtotal=Decimal("35.00"),
            amount_paid=Decimal("35.00"),
            order_status="COMPLETED",
            created_by=self.user,
        )
        credit_sale = Sale.objects.create(
            business=self.business,
            sale_number="CREDIT-001",
            payment_method="CREDIT",
            subtotal=Decimal("100.00"),
            order_status="COMPLETED",
            created_by=self.user,
        )
        Payment.objects.create(
            sale=credit_sale,
            business=self.business,
            amount=Decimal("10.00"),
            payment_method="CASH",
            payment_status="COMPLETED",
            created_by=self.user,
        )

        cash_received, payouts, expected = _drawer_totals(session)

        self.assertEqual(cash_received, Decimal("45.00"))
        self.assertEqual(payouts, Decimal("0"))
        self.assertEqual(expected, Decimal("95.00"))

    def test_drawer_payout_and_variance_reconciliation(self):
        drawer_url = reverse("retail:cash_drawer")
        self.client.post(drawer_url, {
            "action": "open",
            "opening_balance": "100.00",
            "notes": "",
        })
        session = CashDrawerSession.objects.get(closed_at__isnull=True)

        self.client.post(drawer_url, {
            "action": "payout",
            "payout_type": "TRANSPORT",
            "description": "Delivery",
            "recipient": "Courier",
            "amount": "30.00",
        })
        self.client.post(drawer_url, {
            "action": "payout",
            "payout_type": "MISC",
            "description": "Over limit",
            "recipient": "",
            "amount": "80.00",
        })
        self.assertEqual(session.payouts.count(), 1)

        self.client.post(drawer_url, {
            "action": "close",
            "counted_balance": "75.00",
            "variance_reason": "",
        })
        session.refresh_from_db()
        self.assertIsNone(session.closed_at)

        self.client.post(drawer_url, {
            "action": "close",
            "counted_balance": "75.00",
            "variance_reason": "Cash counted at close",
        })
        session.refresh_from_db()
        self.assertIsNotNone(session.closed_at)
        self.assertEqual(session.expected_balance, Decimal("70.00"))
        self.assertEqual(session.variance, Decimal("5.00"))

    def test_credit_payments_update_balance_and_reject_overpayment(self):
        sale = Sale.objects.create(
            business=self.business,
            sale_number="CREDIT-002",
            payment_method="CREDIT",
            subtotal=Decimal("100.00"),
            order_status="COMPLETED",
            created_by=self.user,
        )
        credit_url = reverse("retail:credit")

        self.client.post(credit_url, {
            "action": "payment",
            "sale_id": str(sale.pk),
            "amount": "30.00",
            "payment_method": "CASH",
            "reference_number": "",
            "notes": "",
        })
        sale.refresh_from_db()
        self.assertEqual(sale.balance_due, Decimal("70.00"))
        self.assertEqual(sale.payments.count(), 1)

        self.client.post(credit_url, {
            "action": "payment",
            "sale_id": str(sale.pk),
            "amount": "80.00",
            "payment_method": "CASH",
            "reference_number": "",
            "notes": "",
        })
        self.assertEqual(sale.payments.count(), 1)

    def test_non_retail_business_cannot_open_retail_workspace(self):
        self.business.business_type = "ELECTRONICS"
        self.business.save(update_fields=["business_type"])

        response = self.client.get(reverse("retail:cash_drawer"))

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_user_without_business_cannot_open_retail_workspace(self):
        admin = User.objects.create_user(
            email="admin@example.com",
            password="test-password",
            role="ADMIN",
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("retail:cash_drawer"))

        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
