from django.urls import path

from . import views

app_name = "restaurant"

urlpatterns = [
    path("tables/", views.tables_view, name="tables"),
    path("tables/layout/", views.table_layout_save, name="table_layout_save"),
    path("tables/<uuid:table_id>/<str:action>/", views.table_action, name="table_action"),
    path("reservations/", views.reservations_view, name="reservations"),
    path(
        "reservations/<uuid:reservation_id>/<str:action>/",
        views.reservation_action,
        name="reservation_action",
    ),
    path("kitchen/", views.kitchen_view, name="kitchen"),
    path("kitchen/<uuid:ticket_id>/<str:action>/", views.kitchen_action, name="kitchen_action"),
    path("menu/", views.menu_view, name="menu"),
    path("ingredients/", views.ingredients_view, name="ingredients"),
    path("recipes/", views.recipes_view, name="recipes"),
    path("recipes/<int:recipe_id>/edit/", views.recipes_view, name="recipe_edit"),
    path("recipes/<int:recipe_id>/delete/", views.recipe_delete, name="recipe_delete"),
    path("suppliers/", views.suppliers_view, name="suppliers"),
    path(
        "suppliers/<uuid:supplier_id>/purchase-orders/",
        views.supplier_orders_view,
        name="supplier_orders",
    ),
    path(
        "purchase-orders/<uuid:order_id>/receive/",
        views.purchase_order_receive,
        name="purchase_order_receive",
    ),
    path("cash-drawer/", views.cash_drawer_view, name="cash_drawer"),
    path("food-cost/", views.food_cost_view, name="food_cost"),
]
