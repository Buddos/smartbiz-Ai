from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from products.models import Product
from sales.models import SaleItem

from .models import KitchenTicket, RestaurantRecipe, RestaurantRecipeIngredient


def sync_recipes_using(ingredient_id):
    recipe_ids = RestaurantRecipeIngredient.objects.filter(
        ingredient_id=ingredient_id
    ).values_list("recipe_id", flat=True).distinct()
    for recipe in RestaurantRecipe.objects.filter(pk__in=recipe_ids).prefetch_related(
        "ingredients__ingredient"
    ):
        recipe.sync_menu_item_cost()


@receiver(post_save, sender=Product)
def update_recipe_costs_after_ingredient_price_change(sender, instance, **kwargs):
    if instance.business.business_type == "RESTAURANT":
        sync_recipes_using(instance.pk)


@receiver(post_save, sender=RestaurantRecipeIngredient)
def update_cost_after_recipe_ingredient_save(sender, instance, **kwargs):
    instance.recipe.sync_menu_item_cost()


@receiver(post_delete, sender=RestaurantRecipeIngredient)
def update_cost_after_recipe_ingredient_delete(sender, instance, **kwargs):
    recipe = RestaurantRecipe.objects.filter(pk=instance.recipe_id).first()
    if recipe:
        recipe.sync_menu_item_cost()


@receiver(post_save, sender=SaleItem)
def create_restaurant_kitchen_ticket(sender, instance, **kwargs):
    if instance.sale.business.business_type == "RESTAURANT":
        KitchenTicket.objects.get_or_create(sale=instance.sale)
