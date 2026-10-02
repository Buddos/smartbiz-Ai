import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Chair(models.Model):
    STATUS_CHOICES = [("IDLE", "Idle"), ("BREAK", "On break")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="barber_chairs")
    label = models.CharField(max_length=50)
    barber = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="barber_chairs"
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="IDLE")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["label"]
        constraints = [models.UniqueConstraint(fields=["business", "label"], name="uniq_barber_chair_label")]

    def __str__(self):
        return self.label


class BarberService(models.Model):
    CATEGORY_CHOICES = [
        ("CUT", "Cut"), ("BEARD", "Beard"), ("SHAVE", "Shave"),
        ("KIDS", "Kids"), ("COMBO", "Combo"), ("OTHER", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="barber_services")
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=12, choices=CATEGORY_CHOICES, default="CUT")
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration_min = models.PositiveSmallIntegerField(default=30)
    barbers = models.ManyToManyField("accounts.User", blank=True, related_name="barber_services")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]
        constraints = [models.UniqueConstraint(fields=["business", "name"], name="uniq_barber_service_name")]

    def __str__(self):
        return self.name


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("BOOKED", "Booked"), ("CONFIRMED", "Confirmed"), ("WAITING", "Waiting"),
        ("IN_CHAIR", "In chair"), ("DONE", "Done"), ("NO_SHOW", "No-show"),
        ("CANCELLED", "Cancelled"),
    ]
    SOURCE_CHOICES = [("WALK_IN", "Walk-in"), ("BOOKING", "Booking"), ("PHONE", "Phone")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="barber_appointments")
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.SET_NULL, null=True, blank=True, related_name="barber_appointments"
    )
    client_name = models.CharField(max_length=200, blank=True)
    client_phone = models.CharField(max_length=20, blank=True)
    service = models.ForeignKey(BarberService, on_delete=models.PROTECT, related_name="appointments")
    barber = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="barber_appointments"
    )
    chair = models.ForeignKey(Chair, on_delete=models.SET_NULL, null=True, blank=True, related_name="appointments")
    sale = models.ForeignKey(
        "sales.Sale", on_delete=models.SET_NULL, null=True, blank=True, related_name="barber_appointments"
    )
    start_time = models.DateTimeField(default=timezone.now)
    duration_min = models.PositiveSmallIntegerField(default=30)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="BOOKED")
    source = models.CharField(max_length=12, choices=SOURCE_CHOICES, default="BOOKING")
    priority = models.PositiveSmallIntegerField(default=0)
    checked_in_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-priority", "start_time", "created_at"]
        indexes = [
            models.Index(fields=["business", "start_time", "status"]),
            models.Index(fields=["barber", "status", "start_time"]),
        ]

    @property
    def display_client_name(self):
        return self.client_name or (self.customer.name if self.customer_id else "Walk-in")


class BarberGoal(models.Model):
    METRIC_CHOICES = [
        ("DAILY_REVENUE", "Daily revenue"),
        ("WEEKLY_CUTS", "Weekly cuts"),
        ("MONTHLY_CLIENTS", "Monthly new clients"),
        ("MONTHLY_REVENUE", "Monthly revenue"),
        ("MONTHLY_ATTACH_RATE", "Monthly product attach rate"),
        ("MONTHLY_REPEAT_RATE", "Monthly repeat client rate"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="barber_goals")
    metric = models.CharField(max_length=24, choices=METRIC_CHOICES)
    target = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(1)])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class BarberShift(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey("businesses.Business", on_delete=models.CASCADE, related_name="barber_shifts")
    barber = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="scheduled_barber_shifts"
    )
    chair = models.ForeignKey(Chair, on_delete=models.CASCADE, related_name="scheduled_shifts")
    shift_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_day_off = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["shift_date", "chair__label", "start_time"]
        indexes = [models.Index(fields=["business", "shift_date"])]
