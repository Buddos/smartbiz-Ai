from django.urls import path

from . import views

app_name = "expenses"

urlpatterns = [
    path("", views.expense_list_view, name="list"),
    path("create/", views.expense_create_view, name="create"),
    path("categories/create/", views.category_create_view, name="category_create"),
    path("<uuid:expense_id>/update/", views.expense_update_view, name="update"),
    path("<uuid:expense_id>/delete/", views.expense_delete_view, name="delete"),
]
