from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .events import queue_business_event


def _business_id(instance):
    if getattr(instance, "business_id", None):
        return instance.business_id

    if getattr(instance, "sale_id", None):
        from sales.models import Sale

        return Sale.objects.filter(pk=instance.sale_id).values_list(
            "business_id", flat=True
        ).first()

    if getattr(instance, "menu_item_id", None):
        from products.models import Product

        return Product.objects.filter(pk=instance.menu_item_id).values_list(
            "business_id", flat=True
        ).first()

    if getattr(instance, "recipe_id", None):
        from restaurant.models import RestaurantRecipe

        return RestaurantRecipe.objects.filter(pk=instance.recipe_id).values_list(
            "menu_item__business_id", flat=True
        ).first()

    if getattr(instance, "purchase_order_id", None):
        from restaurant.models import RestaurantPurchaseOrder

        return RestaurantPurchaseOrder.objects.filter(
            pk=instance.purchase_order_id
        ).values_list("business_id", flat=True).first()

    if getattr(instance, "shift_id", None):
        from restaurant.models import RestaurantCashShift

        return RestaurantCashShift.objects.filter(pk=instance.shift_id).values_list(
            "business_id", flat=True
        ).first()

    if getattr(instance, "customer_id", None):
        from customers.models import Customer

        return Customer.objects.filter(pk=instance.customer_id).values_list(
            "business_id", flat=True
        ).first()

    if getattr(instance, "stock_count_id", None):
        from inventory.models import StockCount

        return StockCount.objects.filter(pk=instance.stock_count_id).values_list(
            "business_id", flat=True
        ).first()

    return None


def _publish_model_change(instance, resource, operation):
    queue_business_event(
        _business_id(instance),
        resource,
        operation,
        instance.pk,
    )


def _connect_model(model, resource):
    post_save.connect(
        lambda sender, instance, created, **kwargs: _publish_model_change(
            instance, resource, "created" if created else "updated"
        ),
        sender=model,
        weak=False,
        dispatch_uid=f"realtime_{model._meta.label_lower}_saved",
    )
    post_delete.connect(
        lambda sender, instance, **kwargs: _publish_model_change(
            instance, resource, "deleted"
        ),
        sender=model,
        weak=False,
        dispatch_uid=f"realtime_{model._meta.label_lower}_deleted",
    )


def connect_realtime_signals():
    from accounts.models import User
    from barber.models import Appointment, BarberGoal, BarberService, BarberShift, Chair
    from businesses.models import BusinessSettings
    from customers.models import Customer, CustomerFeedback
    from expenses.models import Expense, ExpenseCategory, RecurringExpense
    from inventory.models import (
        InventoryAlert,
        InventoryTransaction,
        StockCount,
        StockCountItem,
    )
    from products.models import Category, Product
    from restaurant.models import (
        KitchenTicket,
        RestaurantCashMovement,
        RestaurantCashShift,
        RestaurantPurchaseOrder,
        RestaurantPurchaseOrderLine,
        RestaurantRecipe,
        RestaurantRecipeIngredient,
        RestaurantReservation,
        RestaurantSupplier,
        RestaurantTable,
    )
    from salon.models import SalonAppointment, SalonClientPackage, SalonPackageRedemption
    from sales.models import Payment, Return, Sale, SaleItem

    resources = (
        (User, "team"),
        (BusinessSettings, "business_settings"),
        (Category, "menu"),
        (Product, "menu"),
        (Customer, "customers"),
        (CustomerFeedback, "customer_feedback"),
        (Sale, "sales"),
        (SaleItem, "sales"),
        (Payment, "payments"),
        (Return, "sales"),
        (Expense, "expenses"),
        (ExpenseCategory, "expenses"),
        (RecurringExpense, "expenses"),
        (InventoryTransaction, "inventory"),
        (StockCount, "inventory"),
        (StockCountItem, "inventory"),
        (InventoryAlert, "inventory"),
        (RestaurantTable, "restaurant.tables"),
        (RestaurantReservation, "restaurant.reservations"),
        (KitchenTicket, "restaurant.kitchen"),
        (RestaurantRecipe, "restaurant.menu"),
        (RestaurantRecipeIngredient, "restaurant.menu"),
        (RestaurantSupplier, "restaurant.suppliers"),
        (RestaurantPurchaseOrder, "restaurant.purchase_orders"),
        (RestaurantPurchaseOrderLine, "restaurant.purchase_orders"),
        (RestaurantCashShift, "restaurant.cash_drawer"),
        (RestaurantCashMovement, "restaurant.cash_drawer"),
        (Chair, "barber.floor"),
        (BarberService, "barber.services"),
        (Appointment, "barber.appointments"),
        (BarberGoal, "barber.goals"),
        (BarberShift, "barber.schedule"),
        (SalonAppointment, "salon.appointments"),
        (SalonClientPackage, "salon.packages"),
        (SalonPackageRedemption, "salon.packages"),
    )
    for model, resource in resources:
        _connect_model(model, resource)


connect_realtime_signals()
