from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("businesses", "0002_business_enabled_capabilities"),
    ]

    operations = [
        migrations.AlterField(
            model_name="business",
            name="business_type",
            field=models.CharField(
                choices=[
                    ("RETAIL", "Retail Shop"),
                    ("RESTAURANT", "Restaurant"),
                    ("SALON", "Salon"),
                    ("BARBER", "Barbershop"),
                    ("WHOLESALE", "Wholesale"),
                    ("SERVICE", "Service Business"),
                    ("ELECTRONICS", "Electronics Shop"),
                    ("BOUTIQUE", "Boutique"),
                    ("HARDWARE", "Hardware Shop"),
                    ("FREELANCE", "Freelance/Agency"),
                    ("OTHER", "Other"),
                ],
                default="RETAIL",
                max_length=20,
            ),
        ),
    ]
