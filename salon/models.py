import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


class SalonAppointment(models.Model):
    STATUS_CHOICES = [
        ("BOOKED", "Booked"),
        ("CONFIRMED", "Confirmed"),
        ("CHECKED_IN", "Checked in"),
        ("IN_SERVICE", "In service"),
        ("COMPLETED", "Completed"),
        ("NO_SHOW", "No-show"),
        ("CANCELLED", "Cancelled"),
    ]
    SOURCE_CHOICES = [
        ("PHONE", "Phone"),
        ("WALK_IN", "Walk-in"),
        ("INSTAGRAM", "Instagram"),
        ("WHATSAPP", "WhatsApp"),
        ("WEBSITE", "Website"),
        ("OTHER", "Other"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="salon_appointments",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salon_appointments",
    )
    client_name = models.CharField(max_length=200, blank=True)
    client_phone = models.CharField(max_length=20, blank=True)
    services = models.ManyToManyField("products.Product", related_name="salon_appointments")
    stylist = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salon_appointments",
    )
    starts_at = models.DateTimeField(default=timezone.now, db_index=True)
    duration_min = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="BOOKED")
    source = models.CharField(max_length=12, choices=SOURCE_CHOICES, default="PHONE")
    notes = models.TextField(blank=True)
    sale = models.ForeignKey(
        "sales.Sale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salon_appointments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at", "created_at"]
        indexes = [
            models.Index(fields=["business", "starts_at", "status"]),
            models.Index(fields=["business", "stylist", "starts_at"]),
        ]

    @property
    def display_client_name(self):
        return self.client_name or (self.customer.name if self.customer_id else "Walk-in")

    @property
    def display_client_phone(self):
        return self.client_phone or (self.customer.phone if self.customer_id else "")

    def __str__(self):
        return f"{self.display_client_name} · {self.starts_at:%Y-%m-%d %H:%M}"


class SalonClientPackage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="salon_client_packages",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="salon_packages",
    )
    name = models.CharField(max_length=160)
    services = models.ManyToManyField("products.Product", related_name="salon_client_packages")
    sessions_total = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    sessions_redeemed = models.PositiveSmallIntegerField(default=0)
    purchased_at = models.DateField(default=timezone.localdate)
    expires_at = models.DateField(null=True, blank=True)
    purchase_sale = models.ForeignKey(
        "sales.Sale",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salon_client_packages",
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salon_packages_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-purchased_at", "customer__name", "name"]
        constraints = [
            models.CheckConstraint(
                condition=Q(sessions_redeemed__lte=models.F("sessions_total")),
                name="salon_package_redemptions_lte_total",
            ),
        ]
        indexes = [
            models.Index(fields=["business", "customer", "expires_at"]),
        ]

    @property
    def sessions_remaining(self):
        return self.sessions_total - self.sessions_redeemed

    @property
    def is_expired(self):
        return self.expires_at is not None and self.expires_at < timezone.localdate()

    @property
    def is_usable(self):
        return self.sessions_remaining > 0 and not self.is_expired

    def __str__(self):
        return f"{self.name} · {self.customer.name}"


class SalonPackageRedemption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "businesses.Business",
        on_delete=models.CASCADE,
        related_name="salon_package_redemptions",
    )
    client_package = models.ForeignKey(
        SalonClientPackage,
        on_delete=models.CASCADE,
        related_name="redemptions",
    )
    service = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="salon_package_redemptions",
    )
    appointment = models.ForeignKey(
        SalonAppointment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="package_redemptions",
    )
    redeemed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salon_package_redemptions",
    )
    redeemed_at = models.DateTimeField(default=timezone.now)
    notes = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["-redeemed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["client_package", "appointment"],
                condition=Q(appointment__isnull=False),
                name="uniq_salon_package_per_appointment",
            ),
        ]
        indexes = [
            models.Index(fields=["business", "redeemed_at"]),
        ]
