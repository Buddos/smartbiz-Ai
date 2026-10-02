from django.urls import path

from . import views

app_name = "electronics"

urlpatterns = [
    path("suppliers/", views.supplier_list_view, name="suppliers"),
    path("purchase-orders/<uuid:order_id>/receive/", views.purchase_order_receive_view, name="purchase_order_receive"),
    path("repairs/", views.repair_list_view, name="repairs"),
    path("repairs/create/", views.repair_create_view, name="repair_create"),
    path("repairs/<uuid:job_id>/status/", views.repair_status_view, name="repair_status"),
    path("customer-credit/", views.customer_credit_view, name="customer_credit"),
]
