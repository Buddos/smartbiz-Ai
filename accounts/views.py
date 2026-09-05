from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.tokens import default_token_generator
from django.contrib import messages
from django.http import JsonResponse
from django.core.mail import send_mail
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import User, UserActivity, UserSession
from .forms import (
    UserRegistrationForm, UserLoginForm, UserProfileForm,
    UserUpdateForm, PasswordResetForm, PasswordChangeForm
)
from .serializers import UserSerializer, UserActivitySerializer
from .decorators import role_required
import json

User = get_user_model()

# Template Views
def registration_view(request):
    """Handle user registration."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            user.is_active = False
            user.is_email_verified = False
            user.save(update_fields=['is_active', 'is_email_verified'])

            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            verification_url = request.build_absolute_uri(
                reverse('accounts:verify_email', kwargs={'uidb64': uid, 'token': token})
            )
            send_mail(
                'Verify your SmartBiz AI account',
                f'Open this link to verify your account:\n\n{verification_url}',
                None,
                [user.email],
            )
            messages.success(request, 'Registration successful. Check your email to verify your account before signing in.')
            return redirect('accounts:login')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'accounts/register.html', {'form': form})

def login_view(request):
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = UserLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, email=email, password=password)
            
            if user is not None:
                if user.is_active:
                    login(request, user)
                    if not request.session.session_key:
                        request.session.save()
                    
                    # Log login activity
                    UserActivity.objects.create(
                        user=user,
                        action='LOGIN',
                        model_name='User',
                        object_id=str(user.id),
                        ip_address=request.META.get('REMOTE_ADDR'),
                        user_agent=request.META.get('HTTP_USER_AGENT', '')
                    )
                    
                    # Create session record
                    UserSession.objects.create(
                        user=user,
                        session_key=request.session.session_key,
                        ip_address=request.META.get('REMOTE_ADDR'),
                        user_agent=request.META.get('HTTP_USER_AGENT', ''),
                        expires_at=timezone.now() + timezone.timedelta(days=1)
                    )
                    
                    messages.success(request, f'Welcome back, {user.get_full_name()}!')
                    
                    # Redirect to appropriate page
                    next_url = request.GET.get('next')
                    if next_url:
                        return redirect(next_url)
                    return redirect('dashboard')
                else:
                    messages.error(request, 'Your account has been deactivated.')
            else:
                messages.error(request, 'Invalid email or password.')
    else:
        form = UserLoginForm()
    
    return render(request, 'accounts/login.html', {'form': form})


def verify_email_view(request, uidb64, token):
    """Activate a public registration after the email link is confirmed."""
    try:
        user_id = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.is_email_verified = True
        user.save(update_fields=['is_active', 'is_email_verified'])
        messages.success(request, 'Your email has been verified. You can now sign in.')
    else:
        messages.error(request, 'This verification link is invalid or has expired.')
    return redirect('accounts:login')

@login_required
def logout_view(request):
    """Handle user logout."""
    if request.user.is_authenticated:
        # Log logout activity
        UserActivity.objects.create(
            user=request.user,
            action='LOGOUT',
            model_name='User',
            object_id=str(request.user.id),
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        # Update session
        UserSession.objects.filter(
            user=request.user,
            session_key=request.session.session_key
        ).update(is_active=False)
    
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('accounts:login')

@login_required
def profile_view(request):
    """View and edit user profile."""
    user = request.user
    
    if request.method == 'POST':
        form = UserProfileForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('accounts:profile')
    else:
        form = UserProfileForm(instance=user)
    
    # Get recent activity
    activities = UserActivity.objects.filter(user=user)[:10]
    
    return render(request, 'accounts/profile.html', {
        'form': form,
        'activities': activities,
        'user': user
    })

@login_required
@role_required(['OWNER', 'ADMIN', 'SUPER_ADMIN'])
def user_list_view(request):
    """List all users for a business."""
    if request.user.role == 'SUPER_ADMIN':
        users = User.objects.all()
    else:
        business = request.user.business
        if not business:
            messages.error(request, 'No business associated with your account.')
            return redirect('dashboard')
        users = User.objects.filter(business=business)
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        users = users.filter(
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(phone_number__icontains=search_query)
        )
    
    # Pagination
    paginator = Paginator(users, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'accounts/user_list.html', {
        'page_obj': page_obj,
        'search_query': search_query
    })

@login_required
@role_required(['OWNER', 'ADMIN', 'SUPER_ADMIN'])
def user_create_view(request):
    """Create a new user."""
    is_superuser = request.user.is_superuser
    allowed_roles = ['ADMIN'] if is_superuser else ['MANAGER', 'STAFF']
    if request.method == 'POST':
        form = UserRegistrationForm(
            request.POST,
            request.FILES,
            allow_role=True,
            allowed_roles=allowed_roles,
        )
        if form.is_valid():
            user = form.save()
            user.business = None if is_superuser else request.user.business
            user.save()
            
            UserActivity.objects.create(
                user=request.user,
                action='CREATE',
                model_name='User',
                object_id=str(user.id),
                changes={'email': user.email, 'role': user.role},
                business=request.user.business,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            messages.success(request, f'User {user.get_full_name()} created successfully!')
            return redirect('accounts:users_list')
    else:
        form = UserRegistrationForm(allow_role=True, allowed_roles=allowed_roles)
    
    return render(request, 'accounts/user_create.html', {'form': form})

@login_required
@role_required(['OWNER', 'ADMIN', 'SUPER_ADMIN'])
def user_update_view(request, user_id):
    """Update user details."""
    user = get_object_or_404(User, id=user_id)
    
    # Check permissions
    is_superuser = request.user.is_superuser
    if not is_superuser:
        if user.business != request.user.business:
            messages.error(request, 'You do not have permission to edit this user.')
            return redirect('accounts:users_list')
    
    if request.method == 'POST':
        form = UserUpdateForm(
            request.POST,
            request.FILES,
            instance=user,
            allowed_roles=None if is_superuser else ['MANAGER', 'STAFF'],
        )
        if form.is_valid():
            changes = {field: getattr(user, field) for field in ['email', 'role']}
            form.save()
            
            UserActivity.objects.create(
                user=request.user,
                action='UPDATE',
                model_name='User',
                object_id=str(user.id),
                changes=changes,
                business=user.business,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            messages.success(request, f'User {user.get_full_name()} updated successfully!')
            return redirect('accounts:users_list')
    else:
        form = UserUpdateForm(
            instance=user,
            allowed_roles=None if is_superuser else ['MANAGER', 'STAFF'],
        )
    
    return render(request, 'accounts/user_update.html', {
        'form': form,
        'target_user': user
    })

@login_required
@role_required(['OWNER', 'ADMIN', 'SUPER_ADMIN'])
def user_delete_view(request, user_id):
    """Delete a user."""
    user = get_object_or_404(User, id=user_id)
    
    # Prevent self-deletion
    if user == request.user:
        messages.error(request, 'You cannot delete your own account.')
        return redirect('accounts:users_list')
    
    # Check permissions
    if request.user.role != 'SUPER_ADMIN':
        if user.business != request.user.business:
            messages.error(request, 'You do not have permission to delete this user.')
            return redirect('accounts:users_list')
    
    if request.method == 'POST':
        user_email = user.email
        user.delete()
        
        UserActivity.objects.create(
            user=request.user,
            action='DELETE',
            model_name='User',
            object_id=str(user.id),
            changes={'deleted_email': user_email},
            business=request.user.business,
            ip_address=request.META.get('REMOTE_ADDR'),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        messages.success(request, f'User {user_email} deleted successfully!')
        return redirect('accounts:users_list')
    
    return render(request, 'accounts/user_delete.html', {'target_user': user})

# API Views
class UserViewSet(viewsets.ModelViewSet):
    """API viewset for users."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        if user.role == 'SUPER_ADMIN':
            return User.objects.all()
        if user.business:
            return User.objects.filter(business=user.business)
        return User.objects.none()
    
    @action(detail=True, methods=['get'])
    def activities(self, request, pk=None):
        """Get user activities."""
        user = self.get_object()
        activities = UserActivity.objects.filter(user=user)[:50]
        serializer = UserActivitySerializer(activities, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user info."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def permissions(self, request):
        """Get user permissions."""
        return Response(request.user.get_user_permissions_list())