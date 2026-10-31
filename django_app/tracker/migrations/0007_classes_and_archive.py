from django.db import migrations, models


def backfill(apps, schema_editor):
    Student = apps.get_model("tracker", "Student")
    StudioClass = apps.get_model("tracker", "StudioClass")
    Purchase = apps.get_model("tracker", "Purchase")
    existing = set(StudioClass.objects.values_list("name", flat=True))
    students = Student.objects.filter(is_sales_channel=False).exclude(class_name="")
    names = sorted(set(students.values_list("class_name", flat=True)) - existing)
    start = StudioClass.objects.count()
    StudioClass.objects.bulk_create(StudioClass(name=n, sort_order=start + i) for i, n in enumerate(names))
    for purchase in Purchase.objects.select_related("student"):
        purchase.class_name = purchase.student.class_name
        purchase.save(update_fields=["class_name"])


class Migration(migrations.Migration):
    dependencies = [("tracker", "0006_estimate_existing_costs")]

    operations = [
        migrations.RenameModel("ClassOrder", "StudioClass"),
        migrations.RenameField("StudioClass", "class_name", "name"),
        migrations.AlterModelOptions(
            name="studioclass",
            options={"ordering": ["sort_order", "name"], "verbose_name": "class", "verbose_name_plural": "classes"},
        ),
        migrations.AddField("studioclass", "start_date", models.DateField(blank=True, null=True)),
        migrations.AddField(
            "studioclass", "end_date",
            models.DateField(blank=True, null=True, help_text="After this date the class counts as finished."),
        ),
        migrations.AddField("studioclass", "notes", models.TextField(blank=True)),
        migrations.AddField(
            "student", "is_archived",
            models.BooleanField(default=False, help_text="Hidden from everyday lists; history is kept.", verbose_name="archived"),
        ),
        migrations.AddField("student", "archived_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("purchase", "class_name", models.CharField(blank=True, max_length=100, verbose_name="class")),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
