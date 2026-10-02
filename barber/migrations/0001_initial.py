import django.db.models.deletion
import django.utils.timezone
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("accounts", "0003_user_barber_role"),
        ("businesses", "0003_business_barber_type"),
        ("customers", "0001_initial"),
        ("sales", "0002_barber_sale_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="Chair",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("label", models.CharField(max_length=50)),
                ("status", models.CharField(choices=[("IDLE", "Idle"), ("BREAK", "On break")], default="IDLE", max_length=12)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("barber", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="barber_chairs", to="accounts.user")),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="barber_chairs", to="businesses.business")),
            ],
            options={
                "ordering": ["label"],
                "constraints": [models.UniqueConstraint(fields=("business", "label"), name="uniq_barber_chair_label")],
            },
        ),
        migrations.CreateModel(
            name="BarberService",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=120)),
                ("category", models.CharField(choices=[("CUT", "Cut"), ("BEARD", "Beard"), ("SHAVE", "Shave"), ("KIDS", "Kids"), ("COMBO", "Combo"), ("OTHER", "Other")], default="CUT", max_length=12)),
                ("price", models.DecimalField(decimal_places=2, max_digits=10)),
                ("duration_min", models.PositiveSmallIntegerField(default=30)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("barbers", models.ManyToManyField(blank=True, related_name="barber_services", to="accounts.user")),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="barber_services", to="businesses.business")),
            ],
            options={
                "ordering": ["category", "name"],
                "constraints": [models.UniqueConstraint(fields=("business", "name"), name="uniq_barber_service_name")],
            },
        ),
        migrations.CreateModel(
            name="Appointment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("client_name", models.CharField(blank=True, max_length=200)),
                ("client_phone", models.CharField(blank=True, max_length=20)),
                ("start_time", models.DateTimeField(default=django.utils.timezone.now)),
                ("duration_min", models.PositiveSmallIntegerField(default=30)),
                ("status", models.CharField(choices=[("BOOKED", "Booked"), ("CONFIRMED", "Confirmed"), ("WAITING", "Waiting"), ("IN_CHAIR", "In chair"), ("DONE", "Done"), ("NO_SHOW", "No-show"), ("CANCELLED", "Cancelled")], default="BOOKED", max_length=12)),
                ("source", models.CharField(choices=[("WALK_IN", "Walk-in"), ("BOOKING", "Booking"), ("PHONE", "Phone")], default="BOOKING", max_length=12)),
                ("priority", models.PositiveSmallIntegerField(default=0)),
                ("checked_in_at", models.DateTimeField(blank=True, null=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("business", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="barber_appointments", to="businesses.business")),
                ("barber", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="barber_appointments", to="accounts.user")),
                ("chair", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="appointments", to="barber.chair")),
                ("customer", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="barber_appointments", to="customers.customer")),
                ("sale", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="barber_appointments", to="sales.sale")),
                ("service", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="appointments", to="barber.barberservice")),
            ],
            options={
                "ordering": ["-priority", "start_time", "created_at"],
                "indexes": [
                    models.Index(fields=["business", "start_time", "status"], name="barber_appoint_business_4a8f51_idx"),
                    models.Index(fields=["barber", "status", "start_time"], name="barber_appoint_barber_23492c_idx"),
                ],
            },
        ),
    ]
