from django.urls import path

from . import views

app_name = "wholesale"

urlpatterns = [
    path("promotions/", views.promotion_list_view, name="promotions"),
    path("promotions/new/", views.promotion_create_view, name="promotion_create"),
    path("promotions/<uuid:promotion_id>/", views.promotion_detail_view, name="promotion_detail"),
    path("promotions/<uuid:promotion_id>/edit/", views.promotion_edit_view, name="promotion_edit"),
    path("promotions/<uuid:promotion_id>/action/", views.promotion_action_view, name="promotion_action"),
    path("promotions/bulk-action/", views.promotion_bulk_action_view, name="promotion_bulk_action"),
    path("accounts-payable/", views.accounts_payable_view, name="payables"),
    path("accounts-payable/new/", views.supplier_bill_create_view, name="bill_create"),
    path("accounts-payable/<uuid:bill_id>/", views.supplier_bill_detail_view, name="bill_detail"),
    path("accounts-payable/<uuid:bill_id>/edit/", views.supplier_bill_edit_view, name="bill_edit"),
    path("accounts-payable/<uuid:bill_id>/action/", views.supplier_bill_action_view, name="bill_action"),
    path("accounts-payable/schedule-batch/", views.batch_schedule_payments_view, name="batch_schedule"),
]
