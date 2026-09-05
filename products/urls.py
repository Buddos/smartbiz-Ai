from django.urls import path
from . import views

app_name = 'products'

urlpatterns = [
    # Category URLs
    path('categories/', views.category_list_view, name='categories'),
    path('categories/create/', views.category_create_view, name='category_create'),
    path('categories/<uuid:category_id>/update/', views.category_update_view, name='category_update'),
    path('categories/<uuid:category_id>/delete/', views.category_delete_view, name='category_delete'),
    
    # Product URLs
    path('', views.product_list_view, name='list'),
    path('create/', views.product_create_view, name='create'),
    path('<uuid:product_id>/', views.product_detail_view, name='detail'),
    path('<uuid:product_id>/update/', views.product_update_view, name='update'),
    path('<uuid:product_id>/delete/', views.product_delete_view, name='delete'),
    
    # Bulk Operations
    path('bulk-upload/', views.product_bulk_upload_view, name='bulk_upload'),
    path('export/', views.product_export_view, name='export'),
    
    # API Endpoints
    path('api/barcode/', views.get_product_by_barcode, name='api_barcode'),
    path('api/update-stock/', views.update_stock, name='api_update_stock'),
]