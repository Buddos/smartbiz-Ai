from django.urls import path
from . import views

app_name = 'inventory'

urlpatterns = [
    # Dashboard
    path('', views.inventory_dashboard_view, name='dashboard'),
    
    # Transactions
    path('transactions/', views.transaction_list_view, name='transactions'),
    path('transactions/create/', views.transaction_create_view, name='transaction_create'),
    path('transactions/<uuid:transaction_id>/delete/', views.transaction_delete_view, name='transaction_delete'),
    
    # Stock Counts
    path('stock-counts/', views.stock_count_list_view, name='stock_counts'),
    path('stock-counts/create/', views.stock_count_create_view, name='stock_count_create'),
    path('stock-counts/<uuid:stock_count_id>/', views.stock_count_detail_view, name='stock_count_detail'),
    path('stock-counts/<uuid:stock_count_id>/complete/', views.stock_count_complete_view, name='stock_count_complete'),
    
    # Stock Adjustments
    path('adjustment/', views.stock_adjustment_view, name='adjustment'),
    
    # Alerts
    path('alerts/', views.alert_list_view, name='alerts'),
    path('alerts/<uuid:alert_id>/resolve/', views.alert_resolve_view, name='alert_resolve'),
    
    # API Endpoints
    path('api/stats/', views.get_inventory_stats, name='api_stats'),
    path('api/check-alerts/', views.check_stock_alerts, name='api_check_alerts'),
]