import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "studio.settings")

application = get_wsgi_application()

# Only the running server loads this file, so tests and manage.py commands never fetch prices in the background.
from tracker import background  # noqa: E402

background.start()
