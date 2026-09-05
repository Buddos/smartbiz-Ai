from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
import uuid
from businesses.models import Business

class Category(models.Model):
    """Product category model."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='categories')
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Font Awesome icon class")
    color = models.CharField(max_length=20, blank=True, help_text="Hex color code")
    
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategories'
    )
    
    is_active = models.BooleanField(default=True)
    display_order = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'products_category'
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'
        ordering = ['display_order', 'name']
        unique_together = [['business', 'name']]
    
    def __str__(self):
        return self.name
    
    @property
    def full_path(self):
        """Get full category path."""
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name
    
    @property
    def product_count(self):
        """Get number of products in this category."""
        return self.products.filter(is_active=True).count()

class Product(models.Model):
    """Product model for items sold by the business."""
    
    UNIT_CHOICES = [
        ('PCS', 'Pieces'),
        ('KG', 'Kilogram'),
        ('G', 'Gram'),
        ('L', 'Litre'),
        ('ML', 'Millilitre'),
        ('M', 'Meter'),
        ('CM', 'Centimeter'),
        ('BOX', 'Box'),
        ('CARTON', 'Carton'),
        ('BAG', 'Bag'),
        ('BOTTLE', 'Bottle'),
        ('CAN', 'Can'),
        ('PACK', 'Pack'),
        ('ROLL', 'Roll'),
        ('SET', 'Set'),
        ('PAIR', 'Pair'),
        ('DOZEN', 'Dozen'),
        ('OTHER', 'Other'),
    ]
    
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('DISCONTINUED', 'Discontinued'),
        ('OUT_OF_STOCK', 'Out of Stock'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='products')
    
    # Basic Information
    name = models.CharField(max_length=200, db_index=True)
    sku = models.CharField(max_length=50, db_index=True, help_text="Stock Keeping Unit")
    barcode = models.CharField(max_length=50, blank=True, db_index=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products'
    )
    
    # Pricing
    purchase_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0.00
    )
    selling_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0.00
    )
    wholesale_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True,
        blank=True
    )
    discount_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True,
        blank=True
    )
    
    # Inventory
    unit = models.CharField(max_length=20, choices=UNIT_CHOICES, default='PCS')
    current_stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    minimum_stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    maximum_stock = models.IntegerField(null=True, blank=True, validators=[MinValueValidator(0)])
    reorder_level = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    reorder_quantity = models.IntegerField(default=10, validators=[MinValueValidator(1)])
    
    # Supplier Information
    supplier_name = models.CharField(max_length=200, blank=True)
    supplier_contact = models.CharField(max_length=15, blank=True)
    supplier_notes = models.TextField(blank=True)
    
    # Product Details
    description = models.TextField(blank=True)
    weight = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Weight in kg"
    )
    dimensions = models.CharField(max_length=100, blank=True, help_text="L x W x H in cm")
    
    # Images
    image = models.ImageField(upload_to='products/', null=True, blank=True)
    additional_images = models.JSONField(default=list, blank=True, help_text="List of additional image URLs")
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    is_active = models.BooleanField(default=True)
    is_taxable = models.BooleanField(default=True)
    is_serialized = models.BooleanField(default=False, help_text="Track individual items with serial numbers")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'accounts.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='products_created'
    )
    
    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'products_product'
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=["business", "sku"], name="uniq_product_sku_per_business"),
        ]
        indexes = [
            models.Index(fields=['business', 'name']),
            models.Index(fields=['business', 'sku']),
            models.Index(fields=['business', 'category']),
            models.Index(fields=['business', 'status']),
            models.Index(fields=['business', 'current_stock']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.sku})"
    
    @property
    def profit_margin(self):
        """Calculate profit margin percentage."""
        if self.selling_price > 0:
            profit = self.selling_price - self.purchase_price
            return (profit / self.selling_price) * 100
        return 0
    
    @property
    def markup_percentage(self):
        """Calculate markup percentage."""
        if self.purchase_price > 0:
            profit = self.selling_price - self.purchase_price
            return (profit / self.purchase_price) * 100
        return 0
    
    @property
    def stock_value(self):
        """Calculate total stock value."""
        return self.current_stock * self.purchase_price
    
    @property
    def is_low_stock(self):
        """Check if product is low on stock."""
        return self.current_stock <= self.reorder_level
    
    @property
    def is_out_of_stock(self):
        """Check if product is out of stock."""
        return self.current_stock <= 0
    
    @property
    def estimated_days_to_sellout(self, daily_sales_rate=0):
        """Estimate days until stock runs out."""
        if daily_sales_rate > 0 and self.current_stock > 0:
            return self.current_stock / daily_sales_rate
        return None
    
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('products:detail', kwargs={'product_id': self.id})
    
    def save(self, *args, **kwargs):
        # Auto-generate SKU if not provided
        if not self.sku:
            prefix = self.business.name[:3].upper()
            import time
            timestamp = str(int(time.time()))[-6:]
            self.sku = f"{prefix}{timestamp}"
        
        if self.status != "DISCONTINUED":
            if self.current_stock <= 0:
                self.status = "OUT_OF_STOCK"
            else:
                self.status = "ACTIVE"
        
        super().save(*args, **kwargs)

class ProductVariant(models.Model):
    """Product variants (e.g., different sizes, colors)."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    
    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=50, unique=True)
    purchase_price = models.DecimalField(max_digits=12, decimal_places=2)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2)
    current_stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    
    attributes = models.JSONField(default=dict, help_text="Variant attributes (e.g., {'size': 'L', 'color': 'Red'})")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'products_variant'
        verbose_name = 'Product Variant'
        verbose_name_plural = 'Product Variants'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.product.name} - {self.name}"

class ProductImage(models.Model):
    """Product images."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    
    image = models.ImageField(upload_to='products/%Y/%m/%d/')
    caption = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False)
    display_order = models.IntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'products_image'
        verbose_name = 'Product Image'
        verbose_name_plural = 'Product Images'
        ordering = ['display_order']
    
    def __str__(self):
        return f"Image for {self.product.name}"

class ProductReview(models.Model):
    """Product reviews and ratings."""
    
    RATING_CHOICES = [
        (1, '1 Star'),
        (2, '2 Stars'),
        (3, '3 Stars'),
        (4, '4 Stars'),
        (5, '5 Stars'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    customer = models.ForeignKey('customers.Customer', on_delete=models.SET_NULL, null=True, related_name='reviews')
    
    rating = models.IntegerField(choices=RATING_CHOICES)
    review = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'products_review'
        verbose_name = 'Product Review'
        verbose_name_plural = 'Product Reviews'
        ordering = ['-created_at']
        unique_together = [['product', 'customer']]
    
    def __str__(self):
        return f"{self.product.name} - {self.rating} stars"
