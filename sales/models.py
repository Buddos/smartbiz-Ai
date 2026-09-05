from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
import uuid
from businesses.models import Business
from products.models import Product
from customers.models import Customer
from accounts.models import User

class Sale(models.Model):
    """Sales transaction model."""
    
    PAYMENT_STATUS_CHOICES = [
        ('PAID', 'Paid'),
        ('PENDING', 'Pending'),
        ('PARTIAL', 'Partially Paid'),
        ('OVERDUE', 'Overdue'),
        ('REFUNDED', 'Refunded'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('M-PESA', 'M-PESA'),
        ('BANK', 'Bank Transfer'),
        ('CARD', 'Card'),
        ('CREDIT', 'Credit'),
        ('OTHER', 'Other'),
    ]
    
    ORDER_STATUS_CHOICES = [
        ('COMPLETED', 'Completed'),
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('SHIPPED', 'Shipped'),
        ('DELIVERED', 'Delivered'),
        ('CANCELLED', 'Cancelled'),
        ('RETURNED', 'Returned'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='sales')
    
    # Sale Information
    sale_number = models.CharField(max_length=50, unique=True, db_index=True)
    sale_date = models.DateTimeField(default=timezone.now, db_index=True)
    
    # Customer Information
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales'
    )
    customer_name = models.CharField(max_length=200, blank=True)
    customer_phone = models.CharField(max_length=15, blank=True)
    customer_email = models.EmailField(blank=True)
    
    # Financial Details
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0.00
    )
    tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0.00
    )
    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0.00
    )
    shipping = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0.00
    )
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0.00
    )
    
    # Payment Details
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='CASH')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0.00
    )
    balance_due = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0.00
    )
    
    # Order Details
    order_status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='COMPLETED')
    notes = models.TextField(blank=True)
    
    # Staff Information
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='sales_created'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_approved'
    )
    
    # Shipping/Delivery
    delivery_address = models.TextField(blank=True)
    delivery_date = models.DateTimeField(null=True, blank=True)
    tracking_number = models.CharField(max_length=100, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    is_synced = models.BooleanField(default=False)
    synced_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sales_sale'
        verbose_name = 'Sale'
        verbose_name_plural = 'Sales'
        ordering = ['-sale_date']
        indexes = [
            models.Index(fields=['business', 'sale_date']),
            models.Index(fields=['business', 'sale_number']),
            models.Index(fields=['business', 'customer']),
            models.Index(fields=['business', 'payment_status']),
            models.Index(fields=['business', 'order_status']),
        ]
    
    def __str__(self):
        return f"{self.sale_number} - {self.customer_name or 'Walk-in Customer'}"
    
    def save(self, *args, **kwargs):
        if not self.sale_number:
            # Generate sale number: INV-YYYYMMDD-XXXX
            prefix = "INV"
            date_str = timezone.now().strftime('%Y%m%d')
            # Get count of sales for today
            count = Sale.objects.filter(
                business=self.business,
                sale_date__date=timezone.now().date()
            ).count() + 1
            self.sale_number = f"{prefix}-{date_str}-{str(count).zfill(4)}"
        
        self.total = (self.subtotal or 0) + (self.tax or 0) + (self.shipping or 0) - (self.discount or 0)
        self.balance_due = max(0, self.total - (self.amount_paid or 0))
        if self.total > 0 and self.amount_paid >= self.total:
            self.payment_status = "PAID"
        elif self.amount_paid > 0:
            self.payment_status = "PARTIAL"
        elif self.payment_status not in {"REFUNDED"}:
            self.payment_status = "PENDING"
        super().save(*args, **kwargs)

    def recalculate(self):
        items = self.sale_items.all()
        self.subtotal = items.aggregate(total=models.Sum("subtotal"))["total"] or 0
        self.tax = items.aggregate(total=models.Sum("tax_amount"))["total"] or 0
        self.save()
    
    @property
    def profit(self):
        """Calculate profit for the sale."""
        total_cost = self.sale_items.aggregate(
            total=models.Sum(models.F('quantity') * models.F('cost_price'))
        )['total'] or 0
        return self.total - total_cost
    
    @property
    def profit_margin(self):
        """Calculate profit margin percentage."""
        if self.total > 0:
            return (self.profit / self.total) * 100
        return 0
    
    @property
    def item_count(self):
        """Get total number of items sold."""
        return self.sale_items.aggregate(
            total=models.Sum('quantity')
        )['total'] or 0

class SaleItem(models.Model):
    """Individual items in a sale."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='sale_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='sale_items')
    
    # Product details at time of sale
    product_name = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=50)
    unit = models.CharField(max_length=20, default='PCS')
    
    # Pricing details
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Subtotal
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sales_item'
        verbose_name = 'Sale Item'
        verbose_name_plural = 'Sale Items'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['sale', 'product']),
            models.Index(fields=['product', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.product_name} x {self.quantity}"
    
    def save(self, *args, **kwargs):
        if self.product_id:
            if not self.product_name:
                self.product_name = self.product.name
            if not self.product_sku:
                self.product_sku = self.product.sku
            self.unit = self.product.unit
            if not self.cost_price:
                self.cost_price = self.product.purchase_price
            if not self.unit_price:
                self.unit_price = self.product.selling_price
        self.subtotal = self.unit_price * self.quantity
        self.tax_amount = self.subtotal * (self.tax_rate / 100)
        self.total = self.subtotal + self.tax_amount - self.discount
        super().save(*args, **kwargs)

class Payment(models.Model):
    """Payment transactions for sales."""
    
    PAYMENT_METHOD_CHOICES = [
        ('CASH', 'Cash'),
        ('M-PESA', 'M-PESA'),
        ('BANK', 'Bank Transfer'),
        ('CARD', 'Card'),
        ('CREDIT', 'Credit'),
        ('OTHER', 'Other'),
    ]
    
    PAYMENT_STATUS_CHOICES = [
        ('COMPLETED', 'Completed'),
        ('PENDING', 'Pending'),
        ('FAILED', 'Failed'),
        ('REFUNDED', 'Refunded'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='payments')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='payments')
    
    # Payment Details
    payment_number = models.CharField(max_length=50, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='PENDING')
    
    # M-PESA Specific
    mpesa_transaction_id = models.CharField(max_length=50, blank=True)
    mpesa_phone = models.CharField(max_length=15, blank=True)
    mpesa_receipt = models.CharField(max_length=50, blank=True)
    
    # Reference
    reference_number = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    
    # Receipt
    receipt_number = models.CharField(max_length=50, blank=True)
    receipt_sent = models.BooleanField(default=False)
    receipt_sent_at = models.DateTimeField(null=True, blank=True)
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    payment_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='payments_created'
    )
    
    class Meta:
        db_table = 'sales_payment'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-payment_date']
        indexes = [
            models.Index(fields=['business', 'payment_date']),
            models.Index(fields=['business', 'payment_number']),
            models.Index(fields=['sale', 'payment_status']),
        ]
    
    def __str__(self):
        return f"{self.payment_number} - {self.amount}"
    
    def save(self, *args, **kwargs):
        if not self.payment_number:
            prefix = "PAY"
            date_str = timezone.now().strftime('%Y%m%d')
            count = Payment.objects.filter(
                business=self.business,
                payment_date__date=timezone.now().date()
            ).count() + 1
            self.payment_number = f"{prefix}-{date_str}-{str(count).zfill(4)}"
        
        super().save(*args, **kwargs)

class Return(models.Model):
    """Returns and refunds."""
    
    RETURN_STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('PROCESSED', 'Processed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='returns')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='returns')
    
    # Return Details
    return_number = models.CharField(max_length=50, unique=True, db_index=True)
    return_date = models.DateTimeField(default=timezone.now)
    
    # Items Returned
    items = models.JSONField(default=dict, help_text="List of returned items with quantities")
    
    # Financial
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    restocking_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Status
    status = models.CharField(max_length=20, choices=RETURN_STATUS_CHOICES, default='PENDING')
    reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    
    # Approval
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='returns_approved'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='returns_created'
    )
    
    class Meta:
        db_table = 'sales_return'
        verbose_name = 'Return'
        verbose_name_plural = 'Returns'
        ordering = ['-return_date']
        indexes = [
            models.Index(fields=['business', 'return_date']),
            models.Index(fields=['business', 'return_number']),
            models.Index(fields=['sale', 'status']),
        ]
    
    def __str__(self):
        return f"{self.return_number} - {self.sale.sale_number}"
    
    def save(self, *args, **kwargs):
        if not self.return_number:
            prefix = "RET"
            date_str = timezone.now().strftime('%Y%m%d')
            count = Return.objects.filter(
                business=self.business,
                return_date__date=timezone.now().date()
            ).count() + 1
            self.return_number = f"{prefix}-{date_str}-{str(count).zfill(4)}"
        
        super().save(*args, **kwargs)