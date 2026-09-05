from django.urls import path
from . import views

app_name = 'businesses'

urlpatterns = [
    # Business Setup
    path('setup/', views.business_setup, name='setup'),
    
    # Business Settings
    path('settings/', views.business_settings_view, name='settings'),
    path('settings/save/', views.business_settings_save, name='settings_save'),
    
    # Business Management (Admin)
    path('list/', views.business_list_view, name='list'),
    path('<uuid:business_id>/', views.business_detail_view, name='detail'),
    
    # Branches
    path('branches/', views.branch_list_view, name='branches'),
    path('branches/create/', views.branch_create_view, name='branch_create'),
    path('branches/<uuid:branch_id>/update/', views.branch_update_view, name='branch_update'),
    path('branches/<uuid:branch_id>/delete/', views.branch_delete_view, name='branch_delete'),
]