import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0001_initial"),
        ("accounts", "0003_user_barber_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="sale",
            name="barber",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="barber_sales",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="sale",
            name="tip",
            field=models.DecimalField(decimal_places=2, default=0.0, max_digits=10),
        ),
    ]
