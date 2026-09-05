from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.report_list_view, name="list"),
    path("generate/", views.report_generate_view, name="generate"),
    path("<uuid:report_id>/", views.report_detail_view, name="detail"),
]
