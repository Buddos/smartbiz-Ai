from django.db import models
from django.core.validators import MinLengthValidator, MaxLengthValidator
from django.utils import timezone as django_timezone
import uuid
from accounts.models import User

class Business(models.Model):
    """Business model for SMEs."""
    
    BUSINESS_TYPES = [
        ('RETAIL', 'Retail Shop'),
        ('RESTAURANT', 'Restaurant'),
        ('SALON', 'Salon/Barbershop'),
        ('WHOLESALE', 'Wholesale'),
        ('SERVICE', 'Service Business'),
        ('ELECTRONICS', 'Electronics Shop'),
        ('BOUTIQUE', 'Boutique'),
        ('HARDWARE', 'Hardware Shop'),
        ('FREELANCE', 'Freelance/Agency'),
        ('OTHER', 'Other'),
    ]
    
    BUSINESS_SIZES = [
        ('MICRO', 'Micro (1-5 employees)'),
        ('SMALL', 'Small (6-20 employees)'),
        ('MEDIUM', 'Medium (21-50 employees)'),
    ]
    
    # Basic Information
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200, validators=[MinLengthValidator(2)])
    business_type = models.CharField(max_length=20, choices=BUSINESS_TYPES, default='RETAIL')
    business_size = models.CharField(max_length=10, choices=BUSINESS_SIZES, default='MICRO')
    
    # Contact Information
    email = models.EmailField()
    phone_number = models.CharField(max_length=15)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    county = models.CharField(max_length=100, blank=True)
    
    # Location
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    
    # Business Details
    description = models.TextField(blank=True)
    registration_number = models.CharField(max_length=50, blank=True)
    tax_id = models.CharField(max_length=50, blank=True)
    
    # Branding
    logo = models.ImageField(upload_to='business_logos/', null=True, blank=True)
    color_theme = models.JSONField(default=dict, blank=True)
    
    # Settings
    currency = models.CharField(max_length=10, default='KES')
    timezone = models.CharField(max_length=50, default='Africa/Nairobi')
    fiscal_year_start = models.DateField(default=django_timezone.now)
    inventory_valuation_method = models.CharField(
        max_length=20,
        choices=[
            ('FIFO', 'FIFO'),
            ('LIFO', 'LIFO'),
            ('AVERAGE', 'Average Cost')
        ],
        default='FIFO'
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_verified = models.BooleanField(default=False)
    subscription_tier = models.CharField(
        max_length=20,
        choices=[
            ('FREE', 'Free'),
            ('BASIC', 'Basic SME'),
            ('SMART', 'SmartBiz AI'),
            ('PRO', 'Business/Professional')
        ],
        default='FREE'
    )
    subscription_expires = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='businesses_created'
    )
    
    # Preferences
    preferences = models.JSONField(default=dict, blank=True)
    
    class Meta:
        db_table = 'businesses_business'
        verbose_name = 'Business'
        verbose_name_plural = 'Businesses'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['business_type']),
            models.Index(fields=['subscription_tier']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.name
    
    @property
    def is_subscription_active(self):
        """Check if subscription is active."""
        if self.subscription_tier == 'FREE':
            return True
        if self.subscription_expires:
            return django_timezone.now() < self.subscription_expires
        return False
    
    @property
    def employee_count(self):
        """Get number of employees."""
        return self.users.filter(role__in=['OWNER', 'MANAGER', 'STAFF']).count()
    
    def get_full_address(self):
        """Get full formatted address."""
        parts = [self.address, self.city, self.county]
        return ', '.join(filter(None, parts))
    
    def get_settings(self):
        """Get business settings."""
        return {
            'currency': self.currency,
            'timezone': self.timezone,
            'fiscal_year_start': self.fiscal_year_start,
            'inventory_valuation': self.inventory_valuation_method,
            'color_theme': self.color_theme,
        }

class BusinessSettings(models.Model):
    """Extended settings for a business."""
    
    BUSINESS_SETTINGS_CHOICES = [
        ('INVOICE', 'Invoice Settings'),
        ('RECEIPT', 'Receipt Settings'),
        ('EMAIL', 'Email Settings'),
        ('SMS', 'SMS Settings'),
        ('TAX', 'Tax Settings'),
        ('NOTIFICATION', 'Notification Settings'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.OneToOneField(Business, on_delete=models.CASCADE, related_name='settings')
    
    # Invoice Settings
    invoice_prefix = models.CharField(max_length=10, default='INV-')
    invoice_footer = models.TextField(blank=True, help_text="Footer text on invoices")
    invoice_tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=16.00)
    invoice_terms = models.TextField(blank=True)
    
    # Receipt Settings
    receipt_footer = models.TextField(blank=True)
    show_stock_on_receipt = models.BooleanField(default=False)
    
    # Notification Settings
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=False)
    alert_low_stock = models.BooleanField(default=True)
    alert_daily_summary = models.BooleanField(default=True)
    alert_weekly_summary = models.BooleanField(default=True)
    
    # Tax Settings
    tax_enabled = models.BooleanField(default=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=16.00)
    tax_inclusive = models.BooleanField(default=True)
    
    # Email Settings
    email_sender = models.EmailField(blank=True)
    email_subject_prefix = models.CharField(max_length=50, default='SmartBiz AI - ')
    
    # SMS Settings (for future implementation)
    sms_enabled = models.BooleanField(default=False)
    sms_provider = models.CharField(max_length=50, blank=True)
    sms_api_key = models.CharField(max_length=255, blank=True)
    
    # Backup Settings
    auto_backup = models.BooleanField(default=True)
    backup_frequency = models.CharField(
        max_length=20,
        choices=[
            ('DAILY', 'Daily'),
            ('WEEKLY', 'Weekly'),
            ('MONTHLY', 'Monthly')
        ],
        default='DAILY'
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'businesses_settings'
        verbose_name = 'Business Setting'
        verbose_name_plural = 'Business Settings'
    
    def __str__(self):
        return f"Settings for {self.business.name}"

class BusinessBranch(models.Model):
    """Branch/Store model for businesses with multiple locations."""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='branches')
    
    name = models.CharField(max_length=100)
    address = models.TextField()
    city = models.CharField(max_length=100)
    county = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=15)
    email = models.EmailField(blank=True)
    
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    
    is_main = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    
    operating_hours = models.JSONField(default=dict, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'businesses_branch'
        verbose_name = 'Business Branch'
        verbose_name_plural = 'Business Branches'
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} - {self.business.name}"
    
    def save(self, *args, **kwargs):
        if self.is_main:
            # Ensure only one main branch per business
            BusinessBranch.objects.filter(
                business=self.business,
                is_main=True
            ).exclude(id=self.id).update(is_main=False)
        super().save(*args, **kwargs)