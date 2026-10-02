import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from accounts.models import User
from businesses.models import Business
from customers.models import Customer
from products.models import Product
from sales.models import Sale


class RetailSupplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="retail_suppliers")
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    email = models.EmailField(blank=True)
    lead_time_days = models.PositiveSmallIntegerField(default=5)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["business", "name"], name="uniq_retail_supplier_name")
        ]

    def __str__(self):
        return self.name


class RetailPurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SENT", "Sent"),
        ("PARTIAL", "Partially received"),
        ("RECEIVED", "Received"),
        ("CANCELLED", "Cancelled"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="retail_purchase_orders")
    supplier = models.ForeignKey(RetailSupplier, on_delete=models.PROTECT, related_name="purchase_orders")
    order_number = models.CharField(max_length=32, unique=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="DRAFT")
    expected_date = models.DateField(null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="retail_orders_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"RPO-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_number


class RetailPurchaseOrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(RetailPurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="retail_purchase_order_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    received_quantity = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    @property
    def line_total(self):
        return self.quantity * self.unit_cost


class RetailCreditDue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="retail_credit_dues")
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name="retail_credit_due")
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Credit due for {self.sale.sale_number}"


class CashDrawerSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="cash_drawer_sessions")
    opened_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="cash_drawers_opened")
    closed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="cash_drawers_closed"
    )
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    expected_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    counted_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    variance_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-opened_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["business"],
                condition=models.Q(closed_at__isnull=True),
                name="uniq_open_retail_drawer_per_business",
            )
        ]

    def __str__(self):
        return f"Drawer opened {self.opened_at:%Y-%m-%d %H:%M}"


class CashDrawerPayout(models.Model):
    PAYOUT_TYPES = [
        ("SUPPLIER", "Supplier payment"),
        ("STAFF", "Staff advance"),
        ("TRANSPORT", "Transport"),
        ("MISC", "Miscellaneous"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(CashDrawerSession, on_delete=models.CASCADE, related_name="payouts")
    payout_type = models.CharField(max_length=12, choices=PAYOUT_TYPES)
    description = models.CharField(max_length=200)
    recipient = models.CharField(max_length=150, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="cash_drawer_payouts")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.description} - {self.amount}"
