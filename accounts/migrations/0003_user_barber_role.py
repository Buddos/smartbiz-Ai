from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[
                    ("SUPER_ADMIN", "Super Admin"),
                    ("ADMIN", "Platform Admin"),
                    ("OWNER", "Business Owner"),
                    ("MANAGER", "Business Manager"),
                    ("BARBER", "Barber"),
                    ("STAFF", "Staff Member"),
                    ("ACCOUNTANT", "Accountant / Bookkeeper"),
                ],
                default="STAFF",
                max_length=20,
            ),
        ),
    ]
