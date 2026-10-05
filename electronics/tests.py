from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from businesses.models import Business
from customers.models import Customer
from expenses.models import Expense
from inventory.models import InventoryTransaction
from products.models import Product
from sales.models import Sale

from expenses.models import ExpenseCategory, RecurringExpense

from .models import CreditPlan, PurchaseOrder, RepairJob, Supplier


class ElectronicsWorkspaceTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Live Electronics",
            business_type="ELECTRONICS",
            email="shop@example.com",
            phone_number="0700000000",
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
            name="Current handset",
            sku="PHONE-001",
            purchase_price=Decimal("100"),
            selling_price=Decimal("150"),
            current_stock=2,
            reorder_level=3,
            created_by=self.user,
        )
        self.client.force_login(self.user)

    def test_dashboard_uses_live_records_and_electronics_sidebar(self):
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dashboard-readable")
        self.assertNotContains(response, "Electronics sales desk")
        self.assertContains(response, "Current handset")
        self.assertContains(response, reverse("electronics:repairs"))
        self.assertContains(response, 'data-dashboard-account-toggle')
        self.assertContains(response, reverse("business_admin"))
        self.assertContains(response, reverse("businesses:settings"))
        self.assertContains(response, reverse("accounts:profile"))
        self.assertContains(response, reverse("accounts:logout"))
        self.assertLess(
            response.content.index(b"AI Assistant"),
            response.content.index(b"AI Insights"),
        )
        self.assertNotContains(response, "Samsung A15")

    def test_new_purchase_order_link_targets_section_without_suppliers(self):
        response = self.client.get(reverse("electronics:suppliers"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="#purchase-order-section"')
        self.assertContains(response, 'id="purchase-order-section"')
        self.assertContains(response, 'id="supplierConfirmDialog"')
        self.assertContains(response, "Review supplier details")
        self.assertContains(response, "Confirm &amp; add supplier")
        self.assertContains(response, "Add a supplier first to create a purchase order.")
        self.assertNotContains(response, 'id="purchase-order-form"')

    def test_supplier_order_receipt_updates_inventory(self):
        response = self.client.post(reverse("electronics:suppliers"), {
            "form_type": "supplier",
            "supplier-name": "Device Wholesale",
            "supplier-phone": "0700111222",
            "supplier-email": "vendor@example.com",
            "supplier-lead_time_days": "4",
            "supplier-notes": "",
        })
        supplier = Supplier.objects.get(business=self.business)
        self.assertRedirects(response, reverse("electronics:suppliers"))
        supplier_page = self.client.get(reverse("electronics:suppliers"))
        self.assertContains(supplier_page, 'href="#purchase-order-section"')
        self.assertContains(supplier_page, 'id="purchase-order-section"')
        self.assertContains(supplier_page, 'id="purchase-order-form"')

        response = self.client.post(reverse("electronics:suppliers"), {
            "form_type": "order",
            "order-supplier": str(supplier.id),
            "order-product": str(self.product.id),
            "order-quantity": "5",
            "order-unit_cost": "90.00",
            "order-expected_date": "",
            "order-notes": "",
        })
        order = PurchaseOrder.objects.get(business=self.business)
        self.assertRedirects(response, reverse("electronics:suppliers"))
        response = self.client.post(reverse("electronics:purchase_order_receive", args=[order.id]))

        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertRedirects(response, reverse("electronics:suppliers"))
        self.assertEqual(order.status, "RECEIVED")
        self.assertEqual(self.product.current_stock, 7)
        self.assertEqual(
            InventoryTransaction.objects.filter(
                business=self.business, reference_id=str(order.id)
            ).count(),
            1,
        )

    def test_repair_job_creation_and_status_change_are_persisted(self):
        response = self.client.post(reverse("electronics:repair_create"), {
            "customer": "",
            "customer_name": "Amina Customer",
            "customer_phone": "0712345678",
            "device_brand": "Nokia",
            "device_model": "G42",
            "imei": "123456789012345",
            "issue": "Cracked screen",
            "estimate": "4500.00",
            "deposit": "1000.00",
            "promised_date": (date.today() + timedelta(days=2)).isoformat(),
            "technician": "",
            "notes": "",
        })
        job = RepairJob.objects.get(business=self.business)
        self.assertRedirects(response, reverse("electronics:repairs"))

        response = self.client.post(reverse("electronics:repair_status", args=[job.id]), {"status": "READY"})
        job.refresh_from_db()
        self.assertRedirects(response, reverse("electronics:repairs"))
        self.assertEqual(job.status, "READY")

    def test_credit_plan_is_business_scoped_and_balance_comes_from_sale(self):
        customer = Customer.objects.create(
            business=self.business, name="Credit customer", phone="0700000011"
        )
        sale = Sale.objects.create(
            business=self.business,
            customer=customer,
            customer_name=customer.name,
            sale_number="INV-CREDIT-001",
            payment_method="CREDIT",
            subtotal=Decimal("1000"),
            amount_paid=Decimal("250"),
        )
        response = self.client.post(reverse("electronics:customer_credit"), {
            "sale": str(sale.id),
            "installment_count": "3",
            "next_due_date": (date.today() + timedelta(days=7)).isoformat(),
            "notes": "",
        })

        self.assertRedirects(response, reverse("electronics:customer_credit"))
        plan = CreditPlan.objects.get(sale=sale, business=self.business)
        self.assertEqual(plan.balance, Decimal("750"))
        self.assertContains(self.client.get(reverse("electronics:customer_credit")), "Credit customer")

    def test_electronics_pages_show_business_data_and_render_details(self):
        customer = Customer.objects.create(
            business=self.business, name="Live customer", phone="0700000009"
        )
        sale = Sale.objects.create(
            business=self.business,
            customer=customer,
            customer_name=customer.name,
            sale_number="INV-LIVE-001",
            payment_method="CREDIT",
            subtotal=Decimal("500"),
            amount_paid=Decimal("100"),
        )
        category = ExpenseCategory.objects.create(business=self.business, name="Shop rent")
        Expense.objects.create(
            business=self.business,
            category=category,
            title="Actual rent payment",
            amount=Decimal("250"),
            created_by=self.user,
        )
        pages = [
            ("sales:list", "electronics/sales.html"),
            ("expenses:list", "electronics/expenses.html"),
            ("products:list", "electronics/products.html"),
            ("inventory:dashboard", "electronics/inventory.html"),
            ("inventory:transactions", "electronics/inventory_movements.html"),
            ("customers:list", "electronics/customers.html"),
            ("sales:detail", "electronics/sale_detail.html", [sale.id]),
            ("products:detail", "electronics/product_detail.html", [self.product.id]),
            ("customers:detail", "electronics/customer_detail.html", [customer.id]),
        ]
        for page in pages:
            url_name, expected_template, *args = page
            with self.subTest(page=url_name):
                response = self.client.get(reverse(url_name, args=args[0] if args else None))
                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, expected_template)

        self.assertContains(self.client.get(reverse("expenses:list")), "Actual rent payment")
        self.assertContains(self.client.get(reverse("customers:list")), "Live customer")
        self.assertEqual(self.client.get(reverse("customers:export")).get("Content-Type"), "text/csv")
        self.assertEqual(self.client.get(reverse("expenses:export")).get("Content-Type"), "text/csv")
        self.assertEqual(self.client.get(reverse("inventory:export")).get("Content-Type"), "text/csv")

    def test_recurring_expense_requires_confirmation_and_records_one_occurrence(self):
        schedule = RecurringExpense.objects.create(
            business=self.business,
            category=ExpenseCategory.objects.create(business=self.business, name="Internet"),
            title="Internet",
            amount=Decimal("1200.00"),
            frequency="MONTHLY",
            next_due_date=date.today(),
            created_by=self.user,
        )
        response = self.client.post(reverse("expenses:recurring_confirm", args=[schedule.id]))

        self.assertRedirects(response, reverse("expenses:list"))
        self.assertEqual(
            Expense.objects.filter(
                recurring_schedule=schedule,
                recurring_due_date=date.today(),
            ).count(),
            1,
        )
        schedule.refresh_from_db()
        self.assertGreater(schedule.next_due_date, date.today())
