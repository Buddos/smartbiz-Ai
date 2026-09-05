from django.urls import path
from . import views

app_name = 'sales'

urlpatterns = [
    # Sale URLs
    path('', views.sale_list_view, name='list'),
    path('create/', views.sale_create_view, name='create'),
    path('<uuid:sale_id>/', views.sale_detail_view, name='detail'),
    path('<uuid:sale_id>/update/', views.sale_update_view, name='update'),
    path('<uuid:sale_id>/delete/', views.sale_delete_view, name='delete'),
    
    # Payment URLs
    path('<uuid:sale_id>/payment/', views.payment_create_view, name='payment'),
    path('payment/<uuid:payment_id>/receipt/', views.payment_receipt_view, name='receipt'),
    
    # Return URLs
    path('<uuid:sale_id>/return/', views.return_create_view, name='return'),
    
    # Export
    path('export/', views.export_sales_csv, name='export'),
    
    # API Endpoints
    path('api/stats/', views.get_sale_stats, name='api_stats'),
    path('api/invoice/', views.get_sale_by_invoice, name='api_invoice'),
]