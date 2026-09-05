from django.urls import path
from . import views

app_name = 'analytics'

urlpatterns = [
    # Main Dashboard
    path('', views.dashboard_view, name='dashboard'),
    
    # Analytics Pages
    path('sales/', views.sales_analytics_view, name='sales'),
    path('products/', views.product_analytics_view, name='products'),
    path('customers/', views.customer_analytics_view, name='customers'),
    path('financial/', views.financial_analytics_view, name='financial'),
    
    # Insights
    path('generate-insights/', views.generate_insights_view, name='generate_insights'),
    path('insights/<uuid:insight_id>/read/', views.mark_insight_read, name='mark_read'),
    path('insights/<uuid:insight_id>/dismiss/', views.dismiss_insight, name='dismiss'),
    path('insights/<uuid:insight_id>/action/', views.action_insight, name='action'),
    
    # API Endpoints
    path('api/dashboard-data/', views.get_dashboard_data_api, name='api_dashboard'),
]