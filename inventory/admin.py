from django.contrib import admin
from .models import InventoryTransaction, InventoryAlert, StockCount

admin.site.register(InventoryTransaction)
admin.site.register(InventoryAlert)
admin.site.register(StockCount)
