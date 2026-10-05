"""
ASGI config for smartbiz project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/asgi/
"""

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator, OriginValidator
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartbiz.settings')

django_asgi_app = get_asgi_application()

from realtime.routing import websocket_urlpatterns
from django.conf import settings

websocket_application = AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
if settings.WEBSOCKET_ALLOWED_ORIGINS:
    websocket_application = OriginValidator(
        websocket_application,
        settings.WEBSOCKET_ALLOWED_ORIGINS,
    )
else:
    websocket_application = AllowedHostsOriginValidator(websocket_application)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": websocket_application,
})
