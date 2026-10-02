from django.urls import path

from . import views

app_name = "salon"

urlpatterns = [
    path("appointments/", views.appointments, name="appointments"),
    path("bookings/pipeline/", views.bookings_pipeline, name="bookings_pipeline"),
    path("stylists/", views.stylists, name="stylists"),
    path("client-packages/", views.client_packages, name="client_packages"),
    path("services/", views.services, name="services"),
    path("clients/", views.clients, name="clients"),
]
