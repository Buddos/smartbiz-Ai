from django.urls import path

from . import views

app_name = "retail"

urlpatterns = [
    path("suppliers/", views.supplier_list_view, name="suppliers"),
    path("purchase-orders/<uuid:order_id>/receive/", views.purchase_order_receive_view, name="purchase_order_receive"),
    path("cash-drawer/", views.cash_drawer_view, name="cash_drawer"),
    path("credit/", views.credit_view, name="credit"),
]
