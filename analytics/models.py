from django.db import models
from django.utils import timezone
import uuid
from businesses.models import Business
from accounts.models import User

class DashboardWidget(models.Model):
    """Custom dashboard widgets configuration."""
    
    WIDGET_TYPES = [
        ('KPI', 'KPI Card'),
        ('CHART', 'Chart'),
        ('TABLE', 'Table'),
        ('LIST', 'List'),
        ('INSIGHT', 'Insight'),
        ('ALERT', 'Alert'),
    ]
    
    CHART_TYPES = [
        ('LINE', 'Line Chart'),
        ('BAR', 'Bar Chart'),
        ('PIE', 'Pie Chart'),
        ('DOUGHNUT', 'Doughnut Chart'),
        ('AREA', 'Area Chart'),
        ('STACKED_BAR', 'Stacked Bar'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='dashboard_widgets')
    
    # Widget Configuration
    name = models.CharField(max_length=100)
    widget_type = models.CharField(max_length=20, choices=WIDGET_TYPES)
    chart_type = models.CharField(max_length=20, choices=CHART_TYPES, null=True, blank=True)
    
    # Data Configuration
    data_source = models.CharField(max_length=100)  # e.g., 'sales', 'products', 'inventory'
    metric = models.CharField(max_length=100)  # e.g., 'revenue', 'count', 'stock_value'
    aggregation = models.CharField(max_length=20, default='SUM')  # SUM, AVG, COUNT, MAX, MIN
    filters = models.JSONField(default=dict, blank=True)
    
    # Display Configuration
    title = models.CharField(max_length=100)
    subtitle = models.CharField(max_length=200, blank=True)
    icon = models.CharField(max_length=50, blank=True)
    color = models.CharField(max_length=20, blank=True)
    
    # Size & Position
    width = models.IntegerField(default=4)  # 1-12 grid columns
    height = models.IntegerField(default=2)  # 1-4 rows
    position = models.IntegerField(default=0)
    
    # Settings
    is_active = models.BooleanField(default=True)
    refresh_interval = models.IntegerField(default=300, help_text="Refresh interval in seconds")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='dashboard_widgets_created'
    )
    
    class Meta:
        db_table = 'analytics_dashboard_widget'
        verbose_name = 'Dashboard Widget'
        verbose_name_plural = 'Dashboard Widgets'
        ordering = ['position']
    
    def __str__(self):
        return f"{self.name} - {self.business.name}"

class BusinessMetric(models.Model):
    """Historical business metrics for trend analysis."""
    
    METRIC_TYPES = [
        ('REVENUE', 'Revenue'),
        ('SALES_COUNT', 'Sales Count'),
        ('EXPENSES', 'Expenses'),
        ('PROFIT', 'Profit'),
        ('CUSTOMERS', 'Customers'),
        ('PRODUCTS_SOLD', 'Products Sold'),
        ('INVENTORY_VALUE', 'Inventory Value'),
        ('AVERAGE_ORDER_VALUE', 'Average Order Value'),
        ('CUSTOMER_RETENTION', 'Customer Retention'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='metrics')
    
    # Metric Data
    metric_type = models.CharField(max_length=30, choices=METRIC_TYPES)
    date = models.DateField()
    value = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Additional context
    metadata = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'analytics_business_metric'
        verbose_name = 'Business Metric'
        verbose_name_plural = 'Business Metrics'
        unique_together = [['business', 'metric_type', 'date']]
        indexes = [
            models.Index(fields=['business', 'metric_type', 'date']),
            models.Index(fields=['business', 'date']),
        ]
    
    def __str__(self):
        return f"{self.get_metric_type_display()} - {self.date} - {self.value}"

class BusinessInsight(models.Model):
    """AI-generated business insights."""
    
    INSIGHT_TYPES = [
        ('TREND', 'Trend Detected'),
        ('ANOMALY', 'Anomaly Detected'),
        ('OPPORTUNITY', 'Opportunity'),
        ('RISK', 'Risk Identified'),
        ('RECOMMENDATION', 'Recommendation'),
        ('FORECAST', 'Forecast'),
    ]
    
    SEVERITY_CHOICES = [
        ('INFO', 'Information'),
        ('WARNING', 'Warning'),
        ('CRITICAL', 'Critical'),
        ('SUCCESS', 'Success'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='insights')
    
    # Insight Data
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='INFO')
    title = models.CharField(max_length=200)
    description = models.TextField()
    recommendation = models.TextField(blank=True)
    
    # Data Context
    metric = models.CharField(max_length=100, blank=True)
    current_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    previous_value = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    change_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    # Metadata
    data_source = models.CharField(max_length=100, blank=True)
    time_period = models.CharField(max_length=50, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    
    # Status
    is_read = models.BooleanField(default=False)
    is_dismissed = models.BooleanField(default=False)
    is_actioned = models.BooleanField(default=False)
    
    # Timestamps
    generated_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    actioned_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'analytics_business_insight'
        verbose_name = 'Business Insight'
        verbose_name_plural = 'Business Insights'
        ordering = ['-generated_at']
        indexes = [
            models.Index(fields=['business', 'generated_at']),
            models.Index(fields=['business', 'insight_type']),
            models.Index(fields=['business', 'severity']),
            models.Index(fields=['business', 'is_read']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.business.name}"

class ExportLog(models.Model):
    """Track data exports for audit purposes."""
    
    EXPORT_TYPES = [
        ('PDF', 'PDF Report'),
        ('CSV', 'CSV Data'),
        ('EXCEL', 'Excel Spreadsheet'),
        ('JSON', 'JSON Data'),
    ]
    
    EXPORT_MODULES = [
        ('SALES', 'Sales'),
        ('PRODUCTS', 'Products'),
        ('INVENTORY', 'Inventory'),
        ('CUSTOMERS', 'Customers'),
        ('EXPENSES', 'Expenses'),
        ('FINANCIAL', 'Financial'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name='exports')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exports')
    
    # Export Details
    export_type = models.CharField(max_length=20, choices=EXPORT_TYPES)
    module = models.CharField(max_length=20, choices=EXPORT_MODULES)
    file_name = models.CharField(max_length=255)
    file_size = models.IntegerField(default=0, help_text="File size in bytes")
    
    # Parameters
    parameters = models.JSONField(default=dict, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    date_range = models.JSONField(default=dict, blank=True)
    
    # Status
    status = models.CharField(max_length=20, default='COMPLETED')
    error_message = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'analytics_export_log'
        verbose_name = 'Export Log'
        verbose_name_plural = 'Export Logs'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_export_type_display()} - {self.file_name}"