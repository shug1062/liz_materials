from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("tracker", "0008_silver_costing")]

    operations = [
        migrations.CreateModel(
            name="StudioSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("backup_directory", models.CharField(blank=True, max_length=1000, null=True)),
                ("last_backup_date", models.DateField(blank=True, null=True)),
            ],
            options={
                "verbose_name": "studio settings",
                "verbose_name_plural": "studio settings",
            },
        ),
    ]
