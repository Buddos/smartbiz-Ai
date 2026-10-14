from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from businesses.models import Business
from customers.models import Customer
from products.models import Product
from retail.models import RetailSupplier
from sales.models import Sale

from .models import (
    ScheduledSupplierPayment,
    SupplierBill,
    SupplierPayment,
    WholesalePromotion,
    WholesalePromotionRedemption,
)


class WholesalePagesTests(TestCase):
    def setUp(self):
        self.business = Business.objects.create(
            name="Wholesale Test Co",
            email="wholesale@example.com",
            phone_number="0700000000",
            business_type="WHOLESALE",
        )
        self.owner = User.objects.create_user(
            email="wholesale-owner@example.com",
            password="test-password",
            role="OWNER",
            business=self.business,
        )
        self.supplier = RetailSupplier.objects.create(
            business=self.business,
            name="Main Supplier",
        )
        self.product = Product.objects.create(
            business=self.business,
            name="Bulk Rice",
            sku="RICE-001",
            purchase_price=Decimal("60.00"),
            selling_price=Decimal("100.00"),
            current_stock=100,
            created_by=self.owner,
        )
        self.client.force_login(self.owner)

    def make_bill(self, amount=Decimal("100.00"), **overrides):
        return SupplierBill.objects.create(
            business=self.business,
            supplier=self.supplier,
            invoice_number=f"INV-{SupplierBill.objects.count() + 1}",
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=14),
            amount=amount,
            **overrides,
        )

    def test_promotions_and_payables_render_in_shared_wholesale_shell(self):
        for route_name in ("wholesale:promotions", "wholesale:payables"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="wholesale-sidebar"')
                self.assertContains(response, "Inter")
                self.assertContains(response, "data-dashboard-account-menu")
                self.assertContains(response, "Business admin dashboard")
                self.assertContains(response, "Settings")
                self.assertContains(response, "Profile")
                self.assertContains(response, "Log out")

    def test_promotion_and_supplier_invoice_forms_render(self):
        bill = self.make_bill()
        for route_name, args in (
            ("wholesale:promotion_create", ()),
            ("wholesale:bill_create", ()),
            ("wholesale:bill_detail", (bill.pk,)),
            ("wholesale:bill_edit", (bill.pk,)),
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name, args=args))
                self.assertEqual(response.status_code, 200)

    def test_accounts_payable_is_business_scoped(self):
        other_business = Business.objects.create(
            name="Other Wholesale Co",
            email="other@example.com",
            phone_number="0700000001",
            business_type="WHOLESALE",
        )
        other_supplier = RetailSupplier.objects.create(
            business=other_business,
            name="Other Supplier",
        )
        other_bill = SupplierBill.objects.create(
            business=other_business,
            supplier=other_supplier,
            invoice_number="OTHER-INV-1",
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=10),
            amount=Decimal("100.00"),
        )

        response = self.client.get(
            reverse("wholesale:bill_detail", args=[other_bill.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_payment_rejects_overpayment_then_marks_bill_paid(self):
        bill = self.make_bill()
        action_url = reverse("wholesale:bill_action", args=[bill.pk])
        payload = {
            "action": "payment",
            "amount": "101.00",
            "payment_method": "BANK",
            "payment_date": timezone.localdate().isoformat(),
            "reference": "",
            "notes": "",
        }
        response = self.client.post(action_url, payload)
        self.assertRedirects(response, reverse("wholesale:bill_detail", args=[bill.pk]))
        self.assertEqual(SupplierPayment.objects.filter(bill=bill).count(), 0)

        payload["amount"] = "100.00"
        self.client.post(action_url, payload)
        bill.refresh_from_db()
        self.assertEqual(SupplierPayment.objects.filter(bill=bill).count(), 1)
        self.assertEqual(bill.status, "PAID")

    def test_scheduled_payments_cannot_exceed_open_balance(self):
        bill = self.make_bill()
        action_url = reverse("wholesale:bill_action", args=[bill.pk])
        payload = {
            "action": "schedule",
            "amount": "70.00",
            "scheduled_date": (timezone.localdate() + timedelta(days=2)).isoformat(),
            "payment_method": "BANK",
            "notify_user": "on",
        }
        self.client.post(action_url, payload)
        payload["amount"] = "40.00"
        self.client.post(action_url, payload)

        scheduled = ScheduledSupplierPayment.objects.filter(
            bill=bill, status="SCHEDULED",
        )
        self.assertEqual(scheduled.count(), 1)
        self.assertEqual(scheduled.first().amount, Decimal("70.00"))

    def test_invoice_line_products_are_limited_to_the_current_business(self):
        other_business = Business.objects.create(
            name="Other Wholesale Co",
            email="other@example.com",
            phone_number="0700000001",
            business_type="WHOLESALE",
        )
        other_product = Product.objects.create(
            business=other_business,
            name="Other Rice",
            sku="OTHER-RICE",
            created_by=self.owner,
        )
        response = self.client.get(reverse("wholesale:bill_create"))
        product_queryset = response.context["formset"].forms[0].fields["product"].queryset

        self.assertTrue(product_queryset.filter(pk=self.product.pk).exists())
        self.assertFalse(product_queryset.filter(pk=other_product.pk).exists())

    def test_supplier_invoice_accepts_business_scoped_itemized_lines(self):
        response = self.client.post(reverse("wholesale:bill_create"), {
            "supplier": str(self.supplier.pk),
            "invoice_number": "ITEMIZED-001",
            "invoice_date": timezone.localdate().isoformat(),
            "due_date": (timezone.localdate() + timedelta(days=30)).isoformat(),
            "payment_terms": "NET_30",
            "amount": "100.00",
            "bank_details": "",
            "notes": "",
            "lines-TOTAL_FORMS": "1",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-product": str(self.product.pk),
            "lines-0-description": "Two bags",
            "lines-0-quantity": "2",
            "lines-0-unit_cost": "50.00",
            "lines-0-DELETE": "",
        })

        self.assertRedirects(response, reverse("wholesale:payables"))
        bill = SupplierBill.objects.get(invoice_number="ITEMIZED-001")
        self.assertEqual(bill.lines.count(), 1)
        self.assertEqual(bill.lines.get().line_total, Decimal("100.00"))

    def test_invalid_payables_amount_filter_is_reported(self):
        response = self.client.get(reverse("wholesale:payables"), {"min": "not-a-number"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid non-negative amount range.")

    def test_selected_wholesale_promotion_is_applied_and_tracked_on_sale(self):
        customer = Customer.objects.create(
            business=self.business,
            name="Gold Buyer",
            customer_tier="Gold",
        )
        promotion = WholesalePromotion.objects.create(
            business=self.business,
            name="Gold buyer 10 percent",
            promotion_type="PERCENT",
            status="ACTIVE",
            customer_tiers="Gold",
            discount_percent=Decimal("10.00"),
            starts_at=timezone.now() - timedelta(minutes=5),
            ends_at=timezone.now() + timedelta(days=3),
            created_by=self.owner,
        )
        promotion.products.add(self.product)
        response = self.client.get(reverse("sales:create"))
        formset_prefix = response.context["formset"].prefix
        post_data = {
            "customer": str(customer.pk),
            "customer_name": customer.name,
            "customer_phone": "",
            "customer_email": "",
            "payment_method": "CREDIT",
            "discount": "0",
            "notes": "",
            "delivery_address": "",
            "delivery_date": "",
            "promotion_id": str(promotion.pk),
            f"{formset_prefix}-TOTAL_FORMS": "1",
            f"{formset_prefix}-INITIAL_FORMS": "0",
            f"{formset_prefix}-MIN_NUM_FORMS": "1",
            f"{formset_prefix}-MAX_NUM_FORMS": "1000",
            f"{formset_prefix}-0-product": self.product.name,
            f"{formset_prefix}-0-quantity": "2",
            f"{formset_prefix}-0-unit_price": "100.00",
        }

        response = self.client.post(reverse("sales:create"), post_data)

        self.assertEqual(response.status_code, 302)
        sale = Sale.objects.get(business=self.business)
        sale.refresh_from_db()
        self.assertEqual(sale.discount, Decimal("20.00"))
        self.assertEqual(sale.total, Decimal("180.00"))
        redemption = WholesalePromotionRedemption.objects.get(
            promotion=promotion, sale=sale,
        )
        self.assertEqual(redemption.customer, customer)
        self.assertEqual(redemption.eligible_quantity, 2)
        self.assertEqual(redemption.revenue, Decimal("180.00"))
