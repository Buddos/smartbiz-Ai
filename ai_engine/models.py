import uuid

from django.db import models
from django.utils import timezone

from accounts.models import User
from businesses.models import Business


class AIInsight(models.Model):
    INSIGHT_TYPES = [
        ("SALES", "Sales"),
        ("INVENTORY", "Inventory"),
        ("EXPENSE", "Expense"),
        ("CUSTOMER", "Customer"),
        ("PRODUCT", "Product"),
    ]
    SOURCE_CHOICES = [
        ("RULE", "Business rule"),
        ("STAT", "Statistical analysis"),
        ("ML", "Machine learning"),
        ("AI", "AI interpretation"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="ai_insights")
    insight_type = models.CharField(max_length=20, choices=INSIGHT_TYPES)
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default="RULE")
    title = models.CharField(max_length=200)
    observation = models.TextField(help_text="What the data shows")
    interpretation = models.TextField(blank=True, help_text="AI-generated meaning")
    metadata = models.JSONField(default=dict, blank=True)
    insight_kind = models.CharField(max_length=30, default="insight")
    source_model = models.CharField(max_length=80, default="rules.v1")
    severity_score = models.FloatField(default=0.5)
    confidence = models.FloatField(default=0.8)
    score = models.FloatField(default=0.5)
    related_entity_id = models.CharField(max_length=100, blank=True)
    dedupe_key = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, default="active")
    delivery_band = models.CharField(max_length=20, default="background")
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_insights"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    def mark_feedback(self, action):
        self.status = action if action in {"dismissed", "actioned"} else self.status
        self.save(update_fields=["status"])


class AIRecommendation(models.Model):
    PRIORITY = [
        ("HIGH", "High"),
        ("MEDIUM", "Medium"),
        ("LOW", "Low"),
    ]
    STATUS = [
        ("OPEN", "Open"),
        ("ACCEPTED", "Accepted"),
        ("DISMISSED", "Dismissed"),
        ("DONE", "Done"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="ai_recommendations")
    category = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    suggestion = models.TextField()
    priority = models.CharField(max_length=10, choices=PRIORITY, default="MEDIUM")
    status = models.CharField(max_length=12, choices=STATUS, default="OPEN")
    related_insight = models.ForeignKey(
        AIInsight, on_delete=models.SET_NULL, null=True, blank=True, related_name="recommendations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "ai_recommendations"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class AIQuery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="ai_queries")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="ai_queries")
    question = models.TextField()
    answer = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_queries"
        ordering = ["-created_at"]

    def __str__(self):
        return self.question[:80]


class ForecastResult(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="forecast_results")
    metric = models.CharField(max_length=50, default="sales")
    horizon_days = models.PositiveIntegerField(default=7)
    model_name = models.CharField(max_length=80)
    predicted_value = models.DecimalField(max_digits=14, decimal_places=2)
    mae = models.FloatField(null=True, blank=True)
    rmse = models.FloatField(null=True, blank=True)
    mape = models.FloatField(null=True, blank=True)
    series = models.JSONField(default=list, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_forecast_results"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.metric} forecast ({self.horizon_days}d)"


class FeatureSnapshot(models.Model):
    """Cached, tenant-scoped features consumed by intelligence rules and models."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="ai_feature_snapshots")
    product = models.ForeignKey(
        "products.Product", on_delete=models.CASCADE, null=True, blank=True,
        related_name="ai_feature_snapshots"
    )
    captured_at = models.DateTimeField(default=timezone.now)
    feature_date = models.DateField()
    features = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "ai_feature_snapshots"
        ordering = ["-captured_at"]
        indexes = [
            models.Index(fields=["business", "feature_date"]),
            models.Index(fields=["business", "product", "feature_date"]),
        ]


class AIInsightFeedback(models.Model):
    ACTIONS = [("ACCEPTED", "Accepted"), ("DISMISSED", "Dismissed"), ("EDITED", "Edited")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    insight = models.ForeignKey(AIInsight, on_delete=models.CASCADE, related_name="feedback")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="ai_feedback")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="ai_feedback")
    action = models.CharField(max_length=12, choices=ACTIONS)
    model_version = models.CharField(max_length=80)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_insight_feedback"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "action", "created_at"]),
            models.Index(fields=["insight", "created_at"]),
        ]


class InsightDelivery(models.Model):
    CHANNELS = [("DASHBOARD", "Dashboard"), ("EMAIL", "Email"), ("SMS", "SMS")]
    STATUSES = [("PENDING", "Pending"), ("SENT", "Sent"), ("SKIPPED", "Skipped"), ("FAILED", "Failed")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    insight = models.ForeignKey(AIInsight, on_delete=models.CASCADE, related_name="deliveries")
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="ai_deliveries")
    channel = models.CharField(max_length=12, choices=CHANNELS)
    status = models.CharField(max_length=12, choices=STATUSES, default="PENDING")
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ai_insight_deliveries"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["business", "channel", "created_at"]),
            models.Index(fields=["insight", "channel"]),
        ]
