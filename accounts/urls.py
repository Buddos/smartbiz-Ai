from django.contrib.auth import views as auth_views
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    # Authentication
    path('register/', views.registration_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('verify-email/<uidb64>/<token>/', views.verify_email_view, name='verify_email'),
    path(
        'password-reset/',
        auth_views.PasswordResetView.as_view(
            template_name='accounts/password_reset.html',
            email_template_name='accounts/password_reset_email.txt',
            subject_template_name='accounts/password_reset_subject.txt',
        ),
        name='password_reset',
    ),
    path(
        'password-reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='accounts/password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'password-reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='accounts/password_reset_confirm.html',
        ),
        name='password_reset_confirm',
    ),
    path(
        'password-reset/complete/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='accounts/password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
    
    # Profile
    path('profile/', views.profile_view, name='profile'),
    
    # User management
    path('users/', views.user_list_view, name='users_list'),
    path('users/create/', views.user_create_view, name='user_create'),
    path('users/<uuid:user_id>/update/', views.user_update_view, name='user_update'),
    path('users/<uuid:user_id>/delete/', views.user_delete_view, name='user_delete'),
    
    # API endpoints
    path('api/users/', views.UserViewSet.as_view({'get': 'list', 'post': 'create'}), name='api_users'),
    path('api/users/<uuid:pk>/', views.UserViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='api_user_detail'),
    path('api/users/me/', views.UserViewSet.as_view({'get': 'me'}), name='api_user_me'),
    path('api/users/permissions/', views.UserViewSet.as_view({'get': 'permissions'}), name='api_user_permissions'),
]