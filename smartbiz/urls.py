from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from analytics.views import business_admin_dashboard_view, dashboard_view
from smartbiz.views import home, onboarding

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", home, name="home"),
    path("onboarding/", onboarding, name="onboarding"),
    path("dashboard/", dashboard_view, name="dashboard"),
    path("dashboard/admin/", business_admin_dashboard_view, name="business_admin"),
    path("accounts/", include("accounts.urls")),
    path("businesses/", include("businesses.urls")),
    path("products/", include("products.urls")),
    path("sales/", include("sales.urls")),
    path("expenses/", include("expenses.urls")),
    path("inventory/", include("inventory.urls")),
    path("customers/", include("customers.urls")),
    path("analytics/", include("analytics.urls")),
    path("ai/", include("ai_engine.urls")),
    path("reports/", include("reports.urls")),
    path("api/", include("api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "smartbiz.views.custom_404"
handler500 = "smartbiz.views.custom_500"
handler403 = "smartbiz.views.custom_403"
