from django.contrib import admin

from .models import User, UserActivity, UserSession


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "role", "business", "is_active")
    search_fields = ("email", "first_name", "last_name")


admin.site.register(UserActivity)
admin.site.register(UserSession)
