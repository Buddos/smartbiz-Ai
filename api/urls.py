from django.urls import path
from rest_framework.routers import DefaultRouter

from accounts.views import UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="api-users")

urlpatterns = router.urls
