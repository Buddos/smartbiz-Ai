from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
import uuid
from businesses.models import Business
from products.models import Product
from accounts.models import User

class InventoryTransaction(models.Model):
    """Track all inventory movements."""
    
    TRANSACTION_TYPES = [
        ('PURCHASE', 'Purchase'),
        ('SALE', 'Sale'),
        ('RETURN', 'Return'),
        ('ADJUSTMENT', 'Adjustment'),
        ('TRANSFER', 'Transfer'),
        ('WASTE', 'Waste/Damage'),
        ('RECEIVED', 'Received from Supplier'),
        ('RETURNED_TO_SUPPLIER', 'Returned to Supplier'),
        ('INITIAL', 'Initial Stock'),
        ('COUNT', 'Stock Count'),
    ]
    
    TRANSACTION_STATUS = [
        ('PENDING', 'Pending'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('FAILED', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='inventory_transactions')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inventory_transactions')
    
    # Transaction Details
    transaction_type = models.CharField(max_length=25, choices=TRANSACTION_TYPES)
    quantity = models.IntegerField(validators=[MinValueValidator(1)])
    previous_stock = models.IntegerField(default=0)
    new_stock = models.IntegerField(default=0)
    
    # Reference
    reference_type = models.CharField(max_length=50, blank=True)  # e.g., 'SALE', 'PURCHASE'
    reference_id = models.CharField(max_length=100, blank=True)   # ID of related record
    reference_number = models.CharField(max_length=100, blank=True)  # Human-readable reference
    
    # Cost Information
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0.00
    )
    total_cost = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0.00
    )
    
    # Notes
    notes = models.TextField(blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='COMPLETED')
    
    # Approval
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='inventory_transactions_created'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_transactions_approved'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    transaction_date = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'inventory_transaction'
        verbose_name = 'Inventory Transaction'
        verbose_name_plural = 'Inventory Transactions'
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['business', 'transaction_date']),
            models.Index(fields=['business', 'product']),
            models.Index(fields=['business', 'transaction_type']),
            models.Index(fields=['business', 'reference_number']),
        ]
    
    def __str__(self):
        return f"{self.get_transaction_type_display()} - {self.product.name} - {self.quantity}"
    
    def save(self, *args, **kwargs):
        # Calculate total cost
        self.total_cost = self.unit_cost * self.quantity
        
        # Update product stock if completed
        if self.status == 'COMPLETED' and not self.pk:
            # Get current stock before update
            self.previous_stock = self.product.current_stock
            
            if self.transaction_type in ['PURCHASE', 'RETURN', 'RECEIVED', 'INITIAL', 'COUNT', 'TRANSFER']:
                self.new_stock = self.previous_stock + self.quantity
                self.product.current_stock = self.new_stock
            elif self.transaction_type in ['SALE', 'WASTE', 'RETURNED_TO_SUPPLIER']:
                self.new_stock = max(0, self.previous_stock - self.quantity)
                self.product.current_stock = self.new_stock
            elif self.transaction_type == 'ADJUSTMENT':
                # For adjustments, quantity can be positive or negative
                if self.quantity >= 0:
                    self.new_stock = self.previous_stock + self.quantity
                else:
                    self.new_stock = max(0, self.previous_stock + self.quantity)
                self.product.current_stock = self.new_stock
            
            self.product.save()
        
        super().save(*args, **kwargs)

class StockCount(models.Model):
    """Physical stock count records."""
    
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('CANCELLED', 'Cancelled'),
        ('APPROVED', 'Approved'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='stock_counts')
    
    # Count Details
    count_number = models.CharField(max_length=50, unique=True, db_index=True)
    count_date = models.DateField(default=timezone.now)
    
    # Location
    location = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    # Count Results
    expected_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Expected value based on system records"
    )
    actual_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Actual value from physical count"
    )
    difference_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00
    )
    
    # Approval
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='stock_counts_created'
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_counts_approved'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'inventory_stock_count'
        verbose_name = 'Stock Count'
        verbose_name_plural = 'Stock Counts'
        ordering = ['-count_date']
        indexes = [
            models.Index(fields=['business', 'count_date']),
            models.Index(fields=['business', 'status']),
        ]
    
    def __str__(self):
        return f"{self.count_number} - {self.count_date}"
    
    def save(self, *args, **kwargs):
        if not self.count_number:
            prefix = "SC"
            date_str = timezone.now().strftime('%Y%m%d')
            count = StockCount.objects.filter(
                business=self.business,
                count_date=timezone.now().date()
            ).count() + 1
            self.count_number = f"{prefix}-{date_str}-{str(count).zfill(4)}"
        
        super().save(*args, **kwargs)

class StockCountItem(models.Model):
    """Individual items in a stock count."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    stock_count = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='stock_count_items')
    
    # Count Details
    expected_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    counted_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    difference = models.IntegerField(default=0)
    
    # Cost Information
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    expected_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    counted_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    difference_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Notes
    notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'inventory_stock_count_item'
        verbose_name = 'Stock Count Item'
        verbose_name_plural = 'Stock Count Items'
        unique_together = [['stock_count', 'product']]
    
    def __str__(self):
        return f"{self.product.name} - Expected: {self.expected_quantity}, Counted: {self.counted_quantity}"
    
    def save(self, *args, **kwargs):
        self.difference = self.counted_quantity - self.expected_quantity
        self.expected_value = self.expected_quantity * self.unit_cost
        self.counted_value = self.counted_quantity * self.unit_cost
        self.difference_value = self.difference * self.unit_cost
        super().save(*args, **kwargs)

class InventoryAlert(models.Model):
    """Inventory alerts for low stock, expiring items, etc."""
    
    ALERT_TYPES = [
        ('LOW_STOCK', 'Low Stock'),
        ('OUT_OF_STOCK', 'Out of Stock'),
        ('EXPIRY', 'Expiry Date'),
        ('SLOW_MOVING', 'Slow Moving'),
        ('OVERSTOCKED', 'Overstocked'),
    ]
    
    ALERT_SEVERITY = [
        ('INFO', 'Information'),
        ('WARNING', 'Warning'),
        ('CRITICAL', 'Critical'),
    ]
    
    ALERT_STATUS = [
        ('ACTIVE', 'Active'),
        ('RESOLVED', 'Resolved'),
        ('DISMISSED', 'Dismissed'),
        ('IGNORED', 'Ignored'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='inventory_alerts')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='inventory_alerts')
    
    # Alert Details
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    severity = models.CharField(max_length=20, choices=ALERT_SEVERITY, default='WARNING')
    message = models.TextField()
    
    # Current Status
    current_value = models.FloatField(default=0)
    threshold_value = models.FloatField(default=0)
    
    # Status
    status = models.CharField(max_length=20, choices=ALERT_STATUS, default='ACTIVE')
    
    # Resolution
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inventory_alerts_resolved'
    )
    resolution_notes = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'inventory_alert'
        verbose_name = 'Inventory Alert'
        verbose_name_plural = 'Inventory Alerts'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['business', 'status']),
            models.Index(fields=['business', 'alert_type']),
            models.Index(fields=['business', 'severity']),
        ]
    
    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.product.name}"