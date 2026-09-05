from django.contrib import admin
from .models import AIInsight, AIInsightFeedback, AIRecommendation, AIQuery, FeatureSnapshot, ForecastResult, InsightDelivery

admin.site.register(AIInsight)
admin.site.register(AIRecommendation)
admin.site.register(AIQuery)
admin.site.register(ForecastResult)
admin.site.register(FeatureSnapshot)
admin.site.register(AIInsightFeedback)
admin.site.register(InsightDelivery)
