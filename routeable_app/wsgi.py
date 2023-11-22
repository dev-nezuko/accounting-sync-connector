"""WSGI entry point for the connector demo."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'routeable_app.settings')

application = get_wsgi_application()
