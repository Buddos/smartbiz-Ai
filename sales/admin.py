from django.contrib import admin
from .models import Sale, SaleItem, Payment

admin.site.register(Sale)
admin.site.register(SaleItem)
admin.site.register(Payment)
