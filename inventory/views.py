from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.db import models, transaction
from django.db.models import Q, Sum, Count, Avg, F
from django.utils import timezone
from django.views.decorators.http import require_POST
from datetime import datetime, timedelta
import json

from .models import InventoryTransaction, StockCount, StockCountItem, InventoryAlert
from .forms import (
    InventoryTransactionForm, StockCountForm, StockCountItemForm,
    StockAdjustmentForm, InventorySearchForm
)
from products.models import Product
from accounts.models import UserActivity
from accounts.decorators import business_required, role_required

# === Inventory Dashboard ===

@login_required
@business_required
def inventory_dashboard_view(request):
    """Inventory management dashboard."""
    business = request.user.business
    
    # Stock summary
    total_products = Product.objects.filter(business=business, is_active=True).count()
    low_stock_count = Product.objects.filter(
        business=business,
        current_stock__lte=F('reorder_level'),
        current_stock__gt=0,
        is_active=True
    ).count()
    out_of_stock_count = Product.objects.filter(
        business=business,
        current_stock=0,
        is_active=True
    ).count()
    
    # Recent transactions
    recent_transactions = InventoryTransaction.objects.filter(
        business=business
    ).order_by('-transaction_date')[:10]
    
    # Stock value
    stock_value = Product.objects.filter(business=business).aggregate(
        total=Sum(F('current_stock') * F('purchase_price'))
    )['total'] or 0
    
    # Top moving products (based on sales)
    from sales.models import SaleItem
    top_products = SaleItem.objects.filter(
        sale__business=business,
        sale__sale_date__date__gte=timezone.now() - timedelta(days=30)
    ).values('product__name').annotate(
        total_sold=Sum('quantity')
    ).order_by('-total_sold')[:10]
    
    # Alerts
    alerts = InventoryAlert.objects.filter(
        business=business,
        status='ACTIVE'
    ).order_by('-severity', 'created_at')[:10]
    
    context = {
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'stock_value': stock_value,
        'recent_transactions': recent_transactions,
        'top_products': top_products,
        'alerts': alerts,
        'title': 'Inventory Dashboard'
    }
    
    return render(request, 'inventory/dashboard.html', context)

# === Inventory Transactions ===

@login_required
@business_required
def transaction_list_view(request):
    """List all inventory transactions."""
    business = request.user.business
    transactions = InventoryTransaction.objects.filter(business=business)
    
    form = InventorySearchForm(request.GET or None)
    
    if form.is_valid():
        search = form.cleaned_data.get('search')
        if search:
            transactions = transactions.filter(
                Q(product__name__icontains=search) |
                Q(reference_number__icontains=search) |
                Q(reference_type__icontains=search)
            )
        
        transaction_type = form.cleaned_data.get('transaction_type')
        if transaction_type:
            transactions = transactions.filter(transaction_type=transaction_type)
        
        date_from = form.cleaned_data.get('date_from')
        if date_from:
            transactions = transactions.filter(transaction_date__date__gte=date_from)
        
        date_to = form.cleaned_data.get('date_to')
        if date_to:
            transactions = transactions.filter(transaction_date__date__lte=date_to)
        
        status = form.cleaned_data.get('status')
        if status:
            transactions = transactions.filter(status=status)
    
    transactions = transactions.order_by('-transaction_date')
    
    paginator = Paginator(transactions, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Summary stats
    stats = {
        'total_transactions': transactions.count(),
        'total_purchases': transactions.filter(transaction_type='PURCHASE').count(),
        'total_sales': transactions.filter(transaction_type='SALE').count(),
        'total_adjustments': transactions.filter(transaction_type='ADJUSTMENT').count(),
    }
    
    return render(request, 'inventory/transactions.html', {
        'page_obj': page_obj,
        'form': form,
        'stats': stats,
        'title': 'Inventory Transactions'
    })

@login_required
@business_required
def transaction_create_view(request):
    """Create a new inventory transaction."""
    business = request.user.business
    
    if request.method == 'POST':
        form = InventoryTransactionForm(request.POST, business=business)
        if form.is_valid():
            with transaction.atomic():
                transaction_obj = form.save(commit=False)
                transaction_obj.business = business
                transaction_obj.created_by = request.user
                transaction_obj.save()
                
                # Log activity
                UserActivity.objects.create(
                    user=request.user,
                    action='CREATE',
                    model_name='InventoryTransaction',
                    object_id=str(transaction_obj.id),
                    changes={
                        'product': transaction_obj.product.name,
                        'type': transaction_obj.get_transaction_type_display(),
                        'quantity': transaction_obj.quantity
                    },
                    business=business,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                
                messages.success(
                    request,
                    f'Inventory transaction for {transaction_obj.product.name} created successfully!'
                )
                return redirect('inventory:transactions')
    else:
        form = InventoryTransactionForm(business=business)
    
    return render(request, 'inventory/transaction_form.html', {
        'form': form,
        'title': 'New Inventory Transaction'
    })

@login_required
@business_required
@require_POST
def transaction_delete_view(request, transaction_id):
    """Delete an inventory transaction."""
    transaction_obj = get_object_or_404(
        InventoryTransaction,
        id=transaction_id,
        business=request.user.business
    )
    
    if transaction_obj.status == 'COMPLETED':
        messages.error(request, 'Cannot delete a completed transaction.')
        return redirect('inventory:transactions')
    
    transaction_obj.delete()
    messages.success(request, 'Transaction deleted successfully.')
    return redirect('inventory:transactions')

# === Stock Counts ===

@login_required
@business_required
def stock_count_list_view(request):
    """List all stock counts."""
    business = request.user.business
    stock_counts = StockCount.objects.filter(business=business).order_by('-count_date')
    
    paginator = Paginator(stock_counts, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'inventory/stock_counts.html', {
        'page_obj': page_obj,
        'title': 'Stock Counts'
    })

@login_required
@business_required
def stock_count_create_view(request):
    """Create a new stock count."""
    business = request.user.business
    
    if request.method == 'POST':
        form = StockCountForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                stock_count = form.save(commit=False)
                stock_count.business = business
                stock_count.created_by = request.user
                stock_count.save()
                
                messages.success(request, f'Stock count {stock_count.count_number} created successfully!')
                return redirect('inventory:stock_count_detail', stock_count_id=stock_count.id)
    else:
        form = StockCountForm()
    
    return render(request, 'inventory/stock_count_form.html', {
        'form': form,
        'title': 'New Stock Count'
    })

@login_required
@business_required
def stock_count_detail_view(request, stock_count_id):
    """View stock count details."""
    stock_count = get_object_or_404(
        StockCount,
        id=stock_count_id,
        business=request.user.business
    )
    items = stock_count.items.all()
    
    if request.method == 'POST' and stock_count.status == 'DRAFT':
        # Handle adding items
        product_id = request.POST.get('product')
        counted_quantity = request.POST.get('counted_quantity')
        
        if product_id and counted_quantity:
            try:
                product = Product.objects.get(id=product_id, business=request.user.business)
                item, created = StockCountItem.objects.get_or_create(
                    stock_count=stock_count,
                    product=product,
                    defaults={
                        'expected_quantity': product.current_stock,
                        'counted_quantity': int(counted_quantity),
                        'unit_cost': product.purchase_price,
                    }
                )
                if not created:
                    item.counted_quantity = int(counted_quantity)
                    item.save()
                
                messages.success(request, f'Added {product.name} to stock count')
            except Product.DoesNotExist:
                messages.error(request, 'Product not found')
        
        return redirect('inventory:stock_count_detail', stock_count_id=stock_count.id)
    
    # Get products not yet counted
    counted_product_ids = items.values_list('product_id', flat=True)
    available_products = Product.objects.filter(
        business=request.user.business,
        is_active=True
    ).exclude(id__in=counted_product_ids)
    
    return render(request, 'inventory/stock_count_detail.html', {
        'stock_count': stock_count,
        'items': items,
        'available_products': available_products,
        'title': f'Stock Count {stock_count.count_number}'
    })

@login_required
@business_required
@require_POST
def stock_count_complete_view(request, stock_count_id):
    """Complete a stock count and apply adjustments."""
    stock_count = get_object_or_404(
        StockCount,
        id=stock_count_id,
        business=request.user.business
    )
    
    if stock_count.status != 'DRAFT':
        messages.error(request, 'This stock count is already completed.')
        return redirect('inventory:stock_count_detail', stock_count_id=stock_count.id)
    
    with transaction.atomic():
        # Calculate totals
        total_expected = 0
        total_actual = 0
        
        for item in stock_count.items.all():
            total_expected += item.expected_value
            total_actual += item.counted_value
            
            # Update product stock if there's a difference
            if item.difference != 0:
                product = item.product
                product.current_stock = item.counted_quantity
                product.save()
                
                # Create adjustment transaction
                adjustment = InventoryTransaction(
                    business=request.user.business,
                    product=product,
                    transaction_type='COUNT',
                    quantity=abs(item.difference),
                    unit_cost=item.unit_cost,
                    reference_number=stock_count.count_number,
                    notes=f"Stock count adjustment - Expected: {item.expected_quantity}, Counted: {item.counted_quantity}",
                    created_by=request.user,
                    status='COMPLETED'
                )
                adjustment.save()
        
        # Update stock count
        stock_count.expected_total = total_expected
        stock_count.actual_total = total_actual
        stock_count.difference_total = total_actual - total_expected
        stock_count.status = 'COMPLETED'
        stock_count.approved_by = request.user
        stock_count.approved_at = timezone.now()
        stock_count.save()
        
        messages.success(request, f'Stock count {stock_count.count_number} completed successfully!')
    
    return redirect('inventory:stock_count_detail', stock_count_id=stock_count.id)

# === Stock Adjustments ===

@login_required
@business_required
def stock_adjustment_view(request):
    """Quick stock adjustment."""
    business = request.user.business
    
    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST, business=business)
        if form.is_valid():
            with transaction.atomic():
                product = form.cleaned_data['product']
                adjustment_type = form.cleaned_data['adjustment_type']
                quantity = form.cleaned_data['quantity']
                reason = form.cleaned_data['reason']
                
                if adjustment_type == 'add':
                    final_quantity = quantity
                    transaction_type = 'ADJUSTMENT'
                elif adjustment_type == 'subtract':
                    final_quantity = -quantity
                    transaction_type = 'WASTE'
                else:  # set
                    final_quantity = quantity - product.current_stock
                    transaction_type = 'ADJUSTMENT'
                
                # Create transaction
                transaction_obj = InventoryTransaction(
                    business=business,
                    product=product,
                    transaction_type=transaction_type,
                    quantity=abs(final_quantity),
                    unit_cost=product.purchase_price,
                    notes=f"Stock adjustment: {reason}",
                    created_by=request.user,
                    status='COMPLETED'
                )
                
                # For 'set' adjustment, we need to handle differently
                if adjustment_type == 'set':
                    # We'll use the product's current stock as reference
                    transaction_obj.previous_stock = product.current_stock
                    transaction_obj.new_stock = quantity
                    product.current_stock = quantity
                    product.save()
                else:
                    transaction_obj.save()
                
                messages.success(
                    request,
                    f'Stock adjusted for {product.name}. New stock: {product.current_stock}'
                )
                return redirect('inventory:dashboard')
    else:
        form = StockAdjustmentForm(business=business)
    
    return render(request, 'inventory/adjustment.html', {
        'form': form,
        'title': 'Stock Adjustment'
    })

# === Inventory Alerts ===

@login_required
@business_required
def alert_list_view(request):
    """List inventory alerts."""
    business = request.user.business
    alerts = InventoryAlert.objects.filter(business=business)
    
    # Filter
    status_filter = request.GET.get('status', 'ACTIVE')
    if status_filter:
        alerts = alerts.filter(status=status_filter)
    
    alerts = alerts.order_by('-severity', '-created_at')
    
    return render(request, 'inventory/alerts.html', {
        'alerts': alerts,
        'status_filter': status_filter,
        'title': 'Inventory Alerts'
    })

@login_required
@business_required
@require_POST
def alert_resolve_view(request, alert_id):
    """Resolve an inventory alert."""
    alert = get_object_or_404(
        InventoryAlert,
        id=alert_id,
        business=request.user.business
    )
    
    alert.status = 'RESOLVED'
    alert.resolved_at = timezone.now()
    alert.resolved_by = request.user
    alert.resolution_notes = request.POST.get('notes', '')
    alert.save()
    
    messages.success(request, f'Alert for {alert.product.name} resolved.')
    return redirect('inventory:alerts')

# === API Views ===

@login_required
@business_required
def get_inventory_stats(request):
    """Get inventory statistics for dashboard."""
    business = request.user.business
    
    # Stock summary
    total_products = Product.objects.filter(business=business, is_active=True).count()
    low_stock = Product.objects.filter(
        business=business,
        current_stock__lte=F('reorder_level'),
        current_stock__gt=0,
        is_active=True
    ).count()
    out_of_stock = Product.objects.filter(
        business=business,
        current_stock=0,
        is_active=True
    ).count()
    
    # Stock value
    stock_value = Product.objects.filter(business=business).aggregate(
        total=Sum(F('current_stock') * F('purchase_price'))
    )['total'] or 0
    
    # Recent activity
    recent = InventoryTransaction.objects.filter(
        business=business
    ).order_by('-transaction_date')[:5].values(
        'product__name', 'transaction_type', 'quantity', 'transaction_date'
    )
    
    # Low stock products
    low_stock_products = Product.objects.filter(
        business=business,
        current_stock__lte=F('reorder_level'),
        current_stock__gt=0,
        is_active=True
    ).values('name', 'current_stock', 'reorder_level')[:10]
    
    return JsonResponse({
        'total_products': total_products,
        'low_stock': low_stock,
        'out_of_stock': out_of_stock,
        'stock_value': float(stock_value),
        'recent': list(recent),
        'low_stock_products': list(low_stock_products),
    })

@login_required
@business_required
def check_stock_alerts(request):
    """Check and generate stock alerts."""
    business = request.user.business
    
    # Get products that need alerts
    low_stock_products = Product.objects.filter(
        business=business,
        current_stock__lte=F('reorder_level'),
        current_stock__gt=0,
        is_active=True
    )
    
    out_of_stock_products = Product.objects.filter(
        business=business,
        current_stock=0,
        is_active=True
    )
    
    alerts_created = 0
    
    # Create alerts for low stock
    for product in low_stock_products:
        alert, created = InventoryAlert.objects.get_or_create(
            business=business,
            product=product,
            alert_type='LOW_STOCK',
            status='ACTIVE',
            defaults={
                'severity': 'WARNING',
                'message': f'Product "{product.name}" is running low. Current stock: {product.current_stock}, Reorder level: {product.reorder_level}',
                'current_value': product.current_stock,
                'threshold_value': product.reorder_level,
            }
        )
        if created:
            alerts_created += 1
    
    # Create alerts for out of stock
    for product in out_of_stock_products:
        alert, created = InventoryAlert.objects.get_or_create(
            business=business,
            product=product,
            alert_type='OUT_OF_STOCK',
            status='ACTIVE',
            defaults={
                'severity': 'CRITICAL',
                'message': f'Product "{product.name}" is out of stock!',
                'current_value': 0,
                'threshold_value': product.reorder_level,
            }
        )
        if created:
            alerts_created += 1
    
    return JsonResponse({
        'success': True,
        'alerts_created': alerts_created,
        'low_stock_count': low_stock_products.count(),
        'out_of_stock_count': out_of_stock_products.count(),
    })