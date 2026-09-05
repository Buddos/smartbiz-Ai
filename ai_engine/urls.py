from django.urls import path

from . import views

app_name = "ai_engine"

urlpatterns = [
    path("", views.intelligence_home, name="home"),
    path("generate/", views.generate_view, name="generate"),
    path("forecast/", views.forecast_view, name="forecast"),
    path("assistant/", views.assistant_view, name="assistant"),
    path("recommendations/<uuid:rec_id>/<str:status>/", views.recommendation_status, name="rec_status"),
    path("insights/<uuid:insight_id>/feedback/<str:action>/", views.insight_feedback_view, name="insight_feedback"),
]
