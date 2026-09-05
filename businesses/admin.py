from django.contrib import admin
from .models import Business, BusinessSettings, BusinessBranch

admin.site.register(Business)
admin.site.register(BusinessSettings)
admin.site.register(BusinessBranch)
