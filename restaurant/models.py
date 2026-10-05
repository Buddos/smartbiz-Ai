import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class RestaurantTable(models.Model):
    STATUS_CHOICES = [
        ("AVAILABLE", "Available"),
        ("OCCUPIED", "Occupied"),
        ("RESERVED", "Reserved"),
        ("BILL_REQUESTED", "Bill requested"),
        ("NEEDS_ATTENTION", "Needs attention"),
        ("BLOCKED", "Blocked"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="restaurant_tables"
    )
    number = models.CharField(max_length=32)
    zone = models.CharField(max_length=80, default="Indoor")
    seats = models.PositiveSmallIntegerField(default=2, validators=[MinValueValidator(1)])
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="AVAILABLE")
    position_x = models.PositiveSmallIntegerField(default=0)
    position_y = models.PositiveSmallIntegerField(default=0)
    seated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["zone", "number"]
        constraints = [
            models.UniqueConstraint(fields=["business", "number"], name="uniq_restaurant_table_number")
        ]

    def __str__(self):
        return f"Table {self.number}"


class RestaurantReservation(models.Model):
    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("CONFIRMED", "Confirmed"),
        ("SEATED", "Seated"),
        ("CANCELLED", "Cancelled"),
        ("NO_SHOW", "No-show"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="restaurant_reservations"
    )
    table = models.ForeignKey(
        RestaurantTable, on_delete=models.SET_NULL, null=True, blank=True, related_name="reservations"
    )
    code = models.CharField(max_length=24, unique=True, editable=False)
    customer_name = models.CharField(max_length=160)
    phone = models.CharField(max_length=32, blank=True)
    starts_at = models.DateTimeField(db_index=True)
    party_size = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    notes = models.TextField(blank=True)
    deposit = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="PENDING")
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="restaurant_reservations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["business", "starts_at", "status"])]

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = f"R-{timezone.localdate():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.code} · {self.customer_name}"


class KitchenTicket(models.Model):
    STATUS_CHOICES = [
        ("NEW", "New"),
        ("COOKING", "Cooking"),
        ("READY", "Ready"),
        ("COLLECTED", "Collected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale = models.OneToOneField(
        "sales.Sale", on_delete=models.CASCADE, related_name="kitchen_ticket"
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="NEW", db_index=True)
    received_at = models.DateTimeField(default=timezone.now, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["received_at"]

    def transition(self, next_status):
        transitions = {"NEW": "COOKING", "COOKING": "READY", "READY": "COLLECTED"}
        if transitions.get(self.status) != next_status:
            raise ValueError(f"Cannot move a {self.get_status_display()} ticket to {next_status}.")
        now = timezone.now()
        self.status = next_status
        if next_status == "COOKING":
            self.started_at = now
        elif next_status == "READY":
            self.ready_at = now
        else:
            self.collected_at = now
        self.save(update_fields=["status", "started_at", "ready_at", "collected_at", "updated_at"])

    @property
    def sale_items(self):
        return self.sale.sale_items.select_related("product").all()


class RestaurantRecipe(models.Model):
    menu_item = models.OneToOneField(
        "products.Product", on_delete=models.CASCADE, related_name="restaurant_recipe"
    )
    preparation_minutes = models.PositiveSmallIntegerField(default=0)
    method = models.TextField(blank=True)
    yield_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=100,
        validators=[MinValueValidator(Decimal("0.01")), MaxValueValidator(100)],
    )
    waste_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(99.99)],
    )
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def portion_cost(self):
        cached_lines = getattr(self, "_prefetched_objects_cache", {}).get("ingredients")
        lines = cached_lines if cached_lines is not None else list(
            self.ingredients.select_related("ingredient")
        )
        if not lines:
            return None
        ingredient_cost = sum((line.line_cost for line in lines), Decimal("0"))
        yield_ratio = self.yield_percent / Decimal("100")
        waste_ratio = self.waste_percent / Decimal("100")
        if yield_ratio <= 0 or waste_ratio >= 1:
            return Decimal("0")
        return ingredient_cost / yield_ratio / (Decimal("1") - waste_ratio)

    @property
    def margin_percent(self):
        price = self.menu_item.selling_price
        cost = self.portion_cost
        if price <= 0 or cost is None:
            return None
        return (price - cost) * Decimal("100") / price

    @property
    def food_cost_percent(self):
        price = self.menu_item.selling_price
        cost = self.portion_cost
        if price <= 0 or cost is None:
            return None
        return cost * Decimal("100") / price

    def sync_menu_item_cost(self):
        if self.menu_item.business.business_type != "RESTAURANT":
            return
        portion_cost = self.portion_cost
        if portion_cost is not None:
            from products.models import Product

            Product.objects.filter(pk=self.menu_item_id).update(purchase_price=portion_cost)


class RestaurantRecipeIngredient(models.Model):
    recipe = models.ForeignKey(
        RestaurantRecipe, on_delete=models.CASCADE, related_name="ingredients"
    )
    ingredient = models.ForeignKey(
        "products.Product", on_delete=models.PROTECT, related_name="restaurant_recipe_usages"
    )
    quantity = models.DecimalField(max_digits=12, decimal_places=3, validators=[MinValueValidator(Decimal("0.001"))])
    unit = models.CharField(max_length=20, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["recipe", "ingredient"], name="uniq_recipe_ingredient")
        ]

    @property
    def line_cost(self):
        return self.ingredient.purchase_price * self.quantity


class RestaurantSupplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="restaurant_suppliers"
    )
    name = models.CharField(max_length=160)
    contact_name = models.CharField(max_length=160, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["business", "name"], name="uniq_restaurant_supplier_name")
        ]

    def __str__(self):
        return self.name


class RestaurantPurchaseOrder(models.Model):
    STATUS_CHOICES = [
        ("ORDERED", "Ordered"),
        ("RECEIVED", "Received"),
        ("CANCELLED", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="restaurant_purchase_orders"
    )
    supplier = models.ForeignKey(
        RestaurantSupplier, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    order_number = models.CharField(max_length=32, unique=True, editable=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="ORDERED")
    expected_at = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="restaurant_purchase_orders"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["business", "status", "created_at"])]

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = f"PO-{timezone.localdate():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
        super().save(*args, **kwargs)

    @property
    def total_cost(self):
        return sum(
            (
                line.unit_cost * line.quantity
                for line in self.lines.all()
            ),
            Decimal("0"),
        )

    def __str__(self):
        return self.order_number


class RestaurantPurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(
        RestaurantPurchaseOrder, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(
        "products.Product", on_delete=models.PROTECT, related_name="restaurant_purchase_order_lines"
    )
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["purchase_order", "product"],
                name="uniq_restaurant_purchase_order_product",
            )
        ]

    @property
    def line_total(self):
        return self.unit_cost * self.quantity


class RestaurantCashShift(models.Model):
    business = models.ForeignKey(
        "businesses.Business", on_delete=models.CASCADE, related_name="restaurant_cash_shifts"
    )
    opened_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="restaurant_shifts_opened"
    )
    closed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="restaurant_shifts_closed"
    )
    opening_cash = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    closing_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        indexes = [models.Index(fields=["business", "closed_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["business"],
                condition=models.Q(closed_at__isnull=True),
                name="uniq_open_restaurant_cash_shift",
            )
        ]

    @property
    def is_open(self):
        return self.closed_at is None

    @property
    def expected_cash(self):
        from sales.models import Payment

        cash_payments = Payment.objects.filter(
            business=self.business,
            payment_method="CASH",
            payment_status="COMPLETED",
            payment_date__gte=self.opened_at,
        )
        if self.closed_at:
            cash_payments = cash_payments.filter(payment_date__lte=self.closed_at)
        paid = cash_payments.aggregate(total=models.Sum("amount"))["total"] or Decimal("0")
        movements = self.movements.aggregate(
            cash_in=models.Sum("amount", filter=models.Q(movement_type="IN")),
            cash_out=models.Sum("amount", filter=models.Q(movement_type="OUT")),
        )
        return self.opening_cash + paid + (movements["cash_in"] or 0) - (movements["cash_out"] or 0)


class RestaurantCashMovement(models.Model):
    MOVEMENT_CHOICES = [("IN", "Cash in"), ("OUT", "Cash out")]
    shift = models.ForeignKey(RestaurantCashShift, on_delete=models.CASCADE, related_name="movements")
    movement_type = models.CharField(max_length=3, choices=MOVEMENT_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    reason = models.CharField(max_length=240)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="restaurant_cash_movements"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
