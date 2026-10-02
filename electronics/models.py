import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from accounts.models import User
from businesses.models import Business
from customers.models import Customer
from products.models import Product
from sales.models import Sale


class Supplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="electronics_suppliers")
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
            models.UniqueConstraint(fields=["business", "name"], name="uniq_electronics_supplier_name")
        ]

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("SENT", "Sent"),
        ("PARTIAL", "Partially received"),
        ("RECEIVED", "Received"),
        ("CANCELLED", "Cancelled"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="electronics_purchase_orders")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders")
    order_number = models.CharField(max_length=32, unique=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="DRAFT")
    expected_date = models.DateField(null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="electronics_orders_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"PO-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.order_number


class PurchaseOrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="purchase_order_items")
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    received_quantity = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])

    @property
    def line_total(self):
        return self.quantity * self.unit_cost


class RepairJob(models.Model):
    STATUS_CHOICES = [
        ("RECEIVED", "Received"),
        ("DIAGNOSING", "Diagnosing"),
        ("AWAITING_PARTS", "Awaiting parts"),
        ("IN_REPAIR", "In repair"),
        ("READY", "Ready for pickup"),
        ("COLLECTED", "Collected"),
        ("CANCELLED", "Cancelled"),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="repair_jobs")
    job_number = models.CharField(max_length=32, unique=True, blank=True)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL, related_name="repair_jobs")
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=30, blank=True)
    device_brand = models.CharField(max_length=100)
    device_model = models.CharField(max_length=100)
    imei = models.CharField(max_length=100, blank=True)
    issue = models.TextField()
    estimate = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    deposit = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="RECEIVED")
    technician = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="repair_jobs")
    promised_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="repair_jobs_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.job_number:
            self.job_number = f"REP-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.job_number


class CreditPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="credit_plans")
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name="credit_plan")
    installment_count = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    next_due_date = models.DateField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def balance(self):
        return self.sale.balance_due

    @property
    def customer(self):
        return self.sale.customer_name or (self.sale.customer.name if self.sale.customer_id else "Walk-in")

    def __str__(self):
        return f"Credit plan for {self.sale.sale_number}"
