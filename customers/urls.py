from django.urls import path

from . import views

app_name = "customers"

urlpatterns = [
    path("", views.customer_list_view, name="list"),
    path("create/", views.customer_create_view, name="create"),
    path("<uuid:customer_id>/", views.customer_detail_view, name="detail"),
    path("<uuid:customer_id>/update/", views.customer_update_view, name="update"),
    path("<uuid:customer_id>/delete/", views.customer_delete_view, name="delete"),
]
