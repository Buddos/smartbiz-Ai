from django.urls import path

from .consumers import BusinessRealtimeConsumer

websocket_urlpatterns = [
    path("ws/v1/business/", BusinessRealtimeConsumer.as_asgi()),
]
