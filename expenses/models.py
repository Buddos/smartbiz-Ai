import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from accounts.models import User
from businesses.models import Business


class ExpenseCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="expense_categories")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "expenses_category"
        unique_together = [["business", "name"]]
        ordering = ["name"]

    def __str__(self):
        return self.name


class Expense(models.Model):
    PAYMENT_METHODS = [
        ("CASH", "Cash"),
        ("M-PESA", "M-PESA"),
        ("BANK", "Bank Transfer"),
        ("CARD", "Card"),
        ("OTHER", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, related_name="expenses")
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )
    recurring_schedule = models.ForeignKey(
        "RecurringExpense",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="entries",
    )
    recurring_due_date = models.DateField(null=True, blank=True)
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    expense_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS, default="CASH")
    vendor = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    receipt = models.FileField(upload_to="expense_receipts/", null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="expenses_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "expenses_expense"
        ordering = ["-expense_date", "-created_at"]
        indexes = [
            models.Index(fields=["business", "expense_date"]),
            models.Index(fields=["business", "category"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["recurring_schedule", "recurring_due_date"],
                name="unique_recurring_expense_due_entry",
            )
        ]

    def __str__(self):
        return f"{self.title} - {self.amount}"


class RecurringExpense(models.Model):
    FREQUENCY_CHOICES = [
        ("WEEKLY", "Weekly"),
        ("MONTHLY", "Monthly"),
        ("QUARTERLY", "Quarterly"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        Business, on_delete=models.CASCADE, related_name="recurring_expenses"
    )
    category = models.ForeignKey(
        ExpenseCategory,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recurring_schedules",
    )
    title = models.CharField(max_length=200)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    payment_method = models.CharField(max_length=20, choices=Expense.PAYMENT_METHODS, default="CASH")
    vendor = models.CharField(max_length=200, blank=True)
    frequency = models.CharField(max_length=12, choices=FREQUENCY_CHOICES, default="MONTHLY")
    next_due_date = models.DateField()
    anchor_day = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="recurring_expenses_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["next_due_date", "title"]

    def save(self, *args, **kwargs):
        if not self.anchor_day:
            self.anchor_day = self.next_due_date.day
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title
