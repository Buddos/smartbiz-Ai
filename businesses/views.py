from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from .models import Business, BusinessSettings, BusinessBranch
from .forms import BusinessSetupForm, BusinessUpdateForm, BusinessSettingsForm, BusinessBranchForm
from accounts.models import UserActivity
from accounts.decorators import role_required, business_required

@login_required
def business_setup(request):
    """Setup business for first-time owners."""
    
    # Check if user already has a business
    if request.user.business:
        messages.info(request, 'You already have a business set up.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = BusinessSetupForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                # Create the business
                business = form.save(commit=False)
                business.created_by = request.user
                business.save()
                
                # Create default settings
                BusinessSettings.objects.create(business=business)
                
                # Update user with business
                request.user.business = business
                request.user.save()
                
                # Log activity
                UserActivity.objects.create(
                    user=request.user,
                    action='CREATE',
                    model_name='Business',
                    object_id=str(business.id),
                    changes={'name': business.name, 'type': business.business_type},
                    business=business,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                
                messages.success(request, f'Business "{business.name}" created successfully!')
                return redirect('dashboard')
    else:
        form = BusinessSetupForm()
    
    return render(request, 'businesses/setup.html', {
        'form': form,
        'title': 'Set Up Your Business'
    })

@login_required
@business_required
def business_settings_view(request):
    """View and edit business settings."""
    business = request.user.business
    
    if request.method == 'POST':
        form = BusinessUpdateForm(request.POST, request.FILES, instance=business)
        if form.is_valid():
            form.save()
            
            # Log activity
            UserActivity.objects.create(
                user=request.user,
                action='UPDATE',
                model_name='Business',
                object_id=str(business.id),
                changes={'updated': 'business settings'},
                business=business,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            messages.success(request, 'Business settings updated successfully!')
            return redirect('businesses:settings')
    else:
        form = BusinessUpdateForm(instance=business)
    
    # Get settings
    settings, created = BusinessSettings.objects.get_or_create(business=business)
    settings_form = BusinessSettingsForm(instance=settings)
    
    return render(request, 'businesses/settings.html', {
        'business': business,
        'form': form,
        'settings_form': settings_form,
        'title': 'Business Settings'
    })

@login_required
@business_required
@require_POST
def business_settings_save(request):
    """Save business settings via AJAX."""
    business = request.user.business
    settings, created = BusinessSettings.objects.get_or_create(business=business)
    form = BusinessSettingsForm(request.POST, instance=settings)
    
    if form.is_valid():
        form.save()
        return JsonResponse({'success': True, 'message': 'Settings saved successfully!'})
    return JsonResponse({'success': False, 'errors': form.errors})

@login_required
@role_required(['SUPER_ADMIN', 'ADMIN'])
def business_list_view(request):
    """List all businesses (Admin only)."""
    businesses = Business.objects.all().order_by('-created_at')
    
    # Search
    search_query = request.GET.get('search', '')
    if search_query:
        businesses = businesses.filter(
            Q(name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(business_type__icontains=search_query)
        )
    
    # Filter by tier
    tier_filter = request.GET.get('tier', '')
    if tier_filter:
        businesses = businesses.filter(subscription_tier=tier_filter)
    
    paginator = Paginator(businesses, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'businesses/list.html', {
        'page_obj': page_obj,
        'search_query': search_query,
        'tier_filter': tier_filter
    })

@login_required
@role_required(['SUPER_ADMIN', 'ADMIN'])
def business_detail_view(request, business_id):
    """View business details (Admin only)."""
    business = get_object_or_404(Business, id=business_id)
    settings = BusinessSettings.objects.get_or_create(business=business)[0]
    branches = BusinessBranch.objects.filter(business=business)
    users = business.users.all()
    
    return render(request, 'businesses/detail.html', {
        'business': business,
        'settings': settings,
        'branches': branches,
        'users': users
    })

@login_required
@business_required
def branch_list_view(request):
    """List business branches."""
    branches = BusinessBranch.objects.filter(business=request.user.business)
    return render(request, 'businesses/branches.html', {'branches': branches})

@login_required
@business_required
def branch_create_view(request):
    """Create a new branch."""
    if request.method == 'POST':
        form = BusinessBranchForm(request.POST)
        if form.is_valid():
            branch = form.save(commit=False)
            branch.business = request.user.business
            branch.save()
            
            messages.success(request, f'Branch "{branch.name}" created successfully!')
            return redirect('businesses:branches')
    else:
        form = BusinessBranchForm()
    
    return render(request, 'businesses/branch_form.html', {
        'form': form,
        'title': 'Add Branch'
    })

@login_required
@business_required
def branch_update_view(request, branch_id):
    """Update a branch."""
    branch = get_object_or_404(BusinessBranch, id=branch_id, business=request.user.business)
    
    if request.method == 'POST':
        form = BusinessBranchForm(request.POST, instance=branch)
        if form.is_valid():
            form.save()
            messages.success(request, f'Branch "{branch.name}" updated successfully!')
            return redirect('businesses:branches')
    else:
        form = BusinessBranchForm(instance=branch)
    
    return render(request, 'businesses/branch_form.html', {
        'form': form,
        'branch': branch,
        'title': 'Edit Branch'
    })

@login_required
@business_required
@require_POST
def branch_delete_view(request, branch_id):
    """Delete a branch."""
    branch = get_object_or_404(BusinessBranch, id=branch_id, business=request.user.business)
    
    if branch.is_main:
        messages.error(request, 'Cannot delete the main branch.')
        return redirect('businesses:branches')
    
    branch_name = branch.name
    branch.delete()
    messages.success(request, f'Branch "{branch_name}" deleted successfully!')
    return redirect('businesses:branches')

