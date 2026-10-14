from django.contrib import admin
from .models import (
    HardwareQuotation,
    HardwareQuotationItem,
    Payment,
    Sale,
    SaleItem,
)

admin.site.register(Sale)
admin.site.register(SaleItem)
admin.site.register(Payment)
admin.site.register(HardwareQuotation)
admin.site.register(HardwareQuotationItem)
