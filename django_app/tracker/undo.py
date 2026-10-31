"""One-step undo: remember what an action created/deleted so it can be reversed for a few minutes."""
import uuid
from datetime import timedelta

from django.apps import apps
from django.core import serializers
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

SESSION_KEY = "undo"
UNDO_WINDOW = timedelta(minutes=15)


def remember(request, label, created=(), deleted=()):
    request.session[SESSION_KEY] = {
        "id": uuid.uuid4().hex,
        "label": label,
        "created": [[obj._meta.label, obj.pk] for obj in created],
        "deleted": serializers.serialize("json", deleted),
        "at": timezone.now().isoformat(),
        "shown": False,
    }


def offer(request):
    """Context processor: show the Undo bar once, on the page after the action."""
    data = request.session.get(SESSION_KEY) if hasattr(request, "session") else None
    if not data or data.get("shown"):
        return {}
    data["shown"] = True
    request.session.modified = True
    return {"undo_offer": data}


def undo(request, undo_id) -> str | None:
    data = request.session.get(SESSION_KEY)
    if not data or data["id"] != undo_id or timezone.now() - parse_datetime(data["at"]) > UNDO_WINDOW:
        return None
    with transaction.atomic():
        for label, pk in data["created"]:
            apps.get_model(label).objects.filter(pk=pk).delete()
        for restored in serializers.deserialize("json", data["deleted"]):
            restored.save()
    del request.session[SESSION_KEY]
    return data["label"]
