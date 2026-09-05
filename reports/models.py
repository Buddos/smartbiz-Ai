import uuid

from django.db import models

from accounts.models import User
from businesses.models import Business


class Report(models.Model):
    REPORT_TYPES = [
        ("PERFORMANCE", "Business performance"),
        ("SALES", "Sales"),
        ("EXPENSES", "Expenses"),
        ("INVENTORY", "Inventory"),
        ("AI", "AI insights"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="reports")
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    title = models.CharField(max_length=200)
    period_start = models.DateField()
    period_end = models.DateField()
    summary = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="reports_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "reports_report"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
