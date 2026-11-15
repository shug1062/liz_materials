from datetime import date

from django.db import migrations
from django.db.models import Min


def seed_current_projects(apps, schema_editor):
    StudioClass = apps.get_model("tracker", "StudioClass")
    ClassProject = apps.get_model("tracker", "ClassProject")
    Purchase = apps.get_model("tracker", "Purchase")
    PendingMaterial = apps.get_model("tracker", "PendingMaterial")
    db = schema_editor.connection.alias
    # Confirmed start date for the studio's previously undated classes.
    initial_start = date(2026, 11, 15)
    for studio_class in StudioClass.objects.using(db).all():
        if studio_class.end_date and studio_class.end_date < initial_start:
            continue
        if studio_class.start_date is None:
            studio_class.start_date = initial_start
            studio_class.save(using=db, update_fields=["start_date"])
        project_dates = {}
        for model in (Purchase, PendingMaterial):
            records = model.objects.using(db).filter(
                class_name=studio_class.name, project__isnull=False,
                purchase_date__gte=studio_class.start_date,
            )
            if studio_class.end_date:
                records = records.filter(purchase_date__lte=studio_class.end_date)
            for row in records.order_by().values("project_id").annotate(started_on=Min("purchase_date")):
                project_id, started_on = row["project_id"], row["started_on"]
                project_dates[project_id] = min(project_dates.get(project_id, started_on), started_on)
        for project_id, started_on in project_dates.items():
            ClassProject.objects.using(db).get_or_create(
                studio_class_id=studio_class.pk, project_id=project_id, defaults={"started_on": started_on},
            )


class Migration(migrations.Migration):
    dependencies = [("tracker", "0018_alter_studioclass_start_date_classproject")]

    operations = [migrations.RunPython(seed_current_projects, migrations.RunPython.noop)]
