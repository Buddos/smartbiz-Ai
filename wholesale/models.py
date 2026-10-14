import uuid
from decimal import Decimal

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone

from accounts.models import User
from businesses.models import Business
from customers.models import Customer
from products.models import Product
from retail.models import RetailSupplier
from sales.models import Sale


class WholesalePromotion(models.Model):
    TYPES = [
        ("PERCENT", "Percentage off"),
        ("BUY_X_GET_Y", "Buy X Get Y Free"),
        ("VOLUME", "Volume discount"),
        ("BUNDLE", "Bundle"),
        ("SEASONAL", "Seasonal"),
    ]
    STATUSES = [
        ("DRAFT", "Draft"),
        ("SCHEDULED", "Scheduled"),
        ("ACTIVE", "Active"),
        ("PAUSED", "Paused"),
        ("ENDED", "Ended"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="wholesale_promotions"
    )
    name = models.CharField(max_length=180)
    promotion_type = models.CharField(max_length=16, choices=TYPES, default="PERCENT")
    description = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="DRAFT")
    products = models.ManyToManyField(Product, blank=True, related_name="wholesale_promotions")
    customer_tiers = models.CharField(max_length=200, blank=True)
    min_quantity = models.PositiveIntegerField(default=1)
    min_order_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    free_quantity = models.PositiveIntegerField(default=0)
    max_free_per_order = models.PositiveIntegerField(default=0)
    max_uses_per_customer = models.PositiveIntegerField(null=True, blank=True)
    max_total_uses = models.PositiveIntegerField(null=True, blank=True)
    weekdays_only = models.BooleanField(default=False)
    weekends_only = models.BooleanField(default=False)
    exclude_existing_discounts = models.BooleanField(default=True)
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(null=True, blank=True)
    auto_expire = models.BooleanField(default=True)
    notify_sms = models.BooleanField(default=False)
    notify_email = models.BooleanField(default=False)
    notify_in_app = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="wholesale_promotions_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["business", "status", "starts_at"])]

    def __str__(self):
        return self.name

    @property
    def display_status(self):
        now = timezone.now()
        if self.status == "ACTIVE" and self.auto_expire and self.ends_at and self.ends_at < now:
            return "ENDED"
        if self.status in {"ACTIVE", "SCHEDULED"} and self.starts_at > now:
            return "SCHEDULED"
        if self.status == "SCHEDULED" and self.starts_at <= now:
            return "ACTIVE"
        return self.status

    @property
    def tier_list(self):
        return [tier.strip() for tier in self.customer_tiers.split(",") if tier.strip()]


class WholesalePromotionRedemption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    promotion = models.ForeignKey(
        WholesalePromotion, on_delete=models.CASCADE, related_name="redemptions"
    )
    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE, related_name="wholesale_promotion_redemptions"
    )
    customer = models.ForeignKey(
        Customer, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="wholesale_promotion_redemptions",
    )
    customer_name = models.CharField(max_length=200, blank=True)
    eligible_quantity = models.PositiveIntegerField(default=0)
    revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    redeemed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["promotion", "sale"], name="uniq_wholesale_promotion_sale"
            )
        ]
        ordering = ["-redeemed_at"]


class SupplierBill(models.Model):
    TERMS = [
        ("COD", "Cash on delivery"),
        ("NET_15", "Net 15"),
        ("NET_30", "Net 30"),
        ("NET_60", "Net 60"),
        ("ADVANCE", "Advance"),
        ("OTHER", "Other"),
    ]
    STATUSES = [
        ("OPEN", "Open"),
        ("PARTIAL", "Partially paid"),
        ("PAID", "Paid"),
        ("DISPUTED", "Disputed"),
        ("VOID", "Voided"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="supplier_bills"
    )
    supplier = models.ForeignKey(
        RetailSupplier, on_delete=models.PROTECT, related_name="wholesale_bills"
    )
    invoice_number = models.CharField(max_length=80)
    invoice_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField()
    payment_terms = models.CharField(max_length=12, choices=TERMS, default="NET_30")
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)]
    )
    status = models.CharField(max_length=12, choices=STATUSES, default="OPEN")
    bank_details = models.CharField(max_length=250, blank=True)
    notes = models.TextField(blank=True)
    attachment = models.FileField(upload_to="supplier_bills/", null=True, blank=True)
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="supplier_bills_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "supplier__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["business", "supplier", "invoice_number"],
                name="uniq_supplier_invoice_per_business",
            )
        ]
        indexes = [models.Index(fields=["business", "status", "due_date"])]

    def __str__(self):
        return f"{self.invoice_number} · {self.supplier.name}"

    @property
    def amount_paid(self):
        prefetched_payments = getattr(self, "_prefetched_objects_cache", {}).get("payments")
        if prefetched_payments is not None:
            return sum((payment.amount for payment in prefetched_payments), Decimal("0"))
        return self.payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")

    @property
    def balance(self):
        return max(self.amount - self.amount_paid, Decimal("0"))

    @property
    def days_until_due(self):
        return (self.due_date - timezone.localdate()).days

    @property
    def aging_bucket(self):
        days_overdue = -self.days_until_due
        if self.balance <= 0:
            return "PAID"
        if days_overdue <= 0:
            return "CURRENT"
        if days_overdue <= 30:
            return "1_30"
        if days_overdue <= 60:
            return "31_60"
        return "60_PLUS"


class SupplierBillLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bill = models.ForeignKey(SupplierBill, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey(
        Product, null=True, blank=True, on_delete=models.SET_NULL, related_name="supplier_bill_lines"
    )
    description = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )

    @property
    def line_total(self):
        return self.quantity * self.unit_cost


class SupplierPayment(models.Model):
    METHODS = [
        ("BANK", "Bank transfer"),
        ("M-PESA", "M-Pesa"),
        ("CASH", "Cash"),
        ("CHEQUE", "Cheque"),
        ("OTHER", "Other"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    bill = models.ForeignKey(SupplierBill, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)]
    )
    payment_method = models.CharField(max_length=12, choices=METHODS, default="BANK")
    payment_date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    proof = models.FileField(upload_to="supplier_payment_proofs/", null=True, blank=True)
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="supplier_payments_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-created_at"]


class ScheduledSupplierPayment(models.Model):
    STATUSES = [("SCHEDULED", "Scheduled"), ("CANCELLED", "Cancelled"), ("PAID", "Paid")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    bill = models.ForeignKey(
        SupplierBill, on_delete=models.CASCADE, related_name="scheduled_payments"
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)]
    )
    scheduled_date = models.DateField()
    payment_method = models.CharField(max_length=12, choices=SupplierPayment.METHODS, default="BANK")
    notify_user = models.BooleanField(default=True)
    notify_supplier = models.BooleanField(default=False)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="SCHEDULED")
    created_by = models.ForeignKey(
        User, null=True, on_delete=models.SET_NULL, related_name="supplier_payments_scheduled"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_date", "bill__supplier__name"]
