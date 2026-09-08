from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("businesses", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="business",
            name="enabled_capabilities",
            field=models.JSONField(blank=True, default=list),
        ),
    ]