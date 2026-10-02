from django.urls import path

from . import views

app_name = "expenses"

urlpatterns = [
    path("", views.expense_list_view, name="list"),
    path("export/", views.expense_export_view, name="export"),
    path(
        "recurring/<uuid:schedule_id>/confirm/",
        views.recurring_expense_confirm_view,
        name="recurring_confirm",
    ),
    path(
        "recurring/<uuid:schedule_id>/toggle/",
        views.recurring_expense_toggle_view,
        name="recurring_toggle",
    ),
    path("create/", views.expense_create_view, name="create"),
    path("categories/create/", views.category_create_view, name="category_create"),
    path("<uuid:expense_id>/update/", views.expense_update_view, name="update"),
    path("<uuid:expense_id>/delete/", views.expense_delete_view, name="delete"),
]
