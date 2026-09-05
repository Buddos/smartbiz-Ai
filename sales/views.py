from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.db import models, transaction
from django.db.models import Q, Sum, Count, Avg
from django.utils import timezone
from django.views.decorators.http import require_POST
import csv
import json
from datetime import datetime, timedelta

from .models import Sale, SaleItem, Payment, Return
from .forms import SaleForm, SaleItemFormSet, PaymentForm, ReturnForm, SaleSearchForm
from products.models import Product
from customers.models import Customer
from accounts.models import UserActivity
from accounts.decorators import business_required, role_required

# === Sale Views ===

@login_required
@business_required
def sale_list_view(request):
    """List all sales with search and filters."""
    business = request.user.business
    sales = Sale.objects.filter(business=business)
    
    # Search form
    form = SaleSearchForm(request.GET or None)
    
    if form.is_valid():
        # Search by invoice number or customer
        search = form.cleaned_data.get('search')
        if search:
            sales = sales.filter(
                Q(sale_number__icontains=search) |
                Q(customer_name__icontains=search) |
                Q(customer_phone__icontains=search)
            )
        
        # Date range
        date_from = form.cleaned_data.get('date_from')
        if date_from:
            sales = sales.filter(sale_date__date__gte=date_from)
        
        date_to = form.cleaned_data.get('date_to')
        if date_to:
            sales = sales.filter(sale_date__date__lte=date_to)
        
        # Payment status
        payment_status = form.cleaned_data.get('payment_status')
        if payment_status:
            sales = sales.filter(payment_status=payment_status)
        
        # Payment method
        payment_method = form.cleaned_data.get('payment_method')
        if payment_method:
            sales = sales.filter(payment_method=payment_method)
        
        # Amount range
        min_amount = form.cleaned_data.get('min_amount')
        if min_amount:
            sales = sales.filter(total__gte=min_amount)
        
        max_amount = form.cleaned_data.get('max_amount')
        if max_amount:
            sales = sales.filter(total__lte=max_amount)
    
    # Default ordering
    sales = sales.order_by('-sale_date')
    
    # Pagination
    paginator = Paginator(sales, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Summary stats
    today = timezone.now().date()
    today_sales = sales.filter(sale_date__date=today)
    
    stats = {
        'total_sales': sales.count(),
        'today_sales': today_sales.count(),
        'today_revenue': today_sales.aggregate(total=Sum('total'))['total'] or 0,
        'total_revenue': sales.aggregate(total=Sum('total'))['total'] or 0,
        'average_sale': sales.aggregate(avg=Avg('total'))['avg'] or 0,
        'pending_payments': sales.filter(payment_status='PENDING').count(),
    }
    
    return render(request, 'sales/list.html', {
        'page_obj': page_obj,
        'form': form,
        'stats': stats,
        'title': 'Sales',
    })

@login_required
@business_required
def sale_create_view(request):
    """Create a new sale."""
    business = request.user.business
    
    if request.method == 'POST':
        form = SaleForm(request.POST, business=business)
        formset = SaleItemFormSet(request.POST, business=business)
        
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                # Create sale
                sale = form.save(commit=False)
                sale.business = business
                sale.created_by = request.user
                sale.save()
                
                formset.instance = sale
                formset.save()
                sale.recalculate()
                if sale.payment_method in {"CASH", "M-PESA", "CARD", "BANK"} and sale.amount_paid == 0:
                    sale.amount_paid = sale.total
                    sale.save()
                for item_form in formset:
                    if item_form.cleaned_data and not item_form.cleaned_data.get("DELETE", False):
                        product = item_form.cleaned_data["product"]
                        quantity = item_form.cleaned_data["quantity"]
                        product.current_stock = max(0, product.current_stock - quantity)
                        product.save()
                
                # Log activity
                UserActivity.objects.create(
                    user=request.user,
                    action='CREATE',
                    model_name='Sale',
                    object_id=str(sale.id),
                    changes={'sale_number': sale.sale_number, 'total': float(sale.total)},
                    business=business,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                
                messages.success(request, f'Sale #{sale.sale_number} created successfully!')
                return redirect('sales:detail', sale_id=sale.id)
    else:
        form = SaleForm(business=business)
        formset = SaleItemFormSet(business=business)
    
    return render(request, 'sales/form.html', {
        'form': form,
        'formset': formset,
        'title': 'New Sale',
    })

@login_required
@business_required
def sale_detail_view(request, sale_id):
    """View sale details."""
    sale = get_object_or_404(Sale, id=sale_id, business=request.user.business)
    items = sale.sale_items.all()
    payments = sale.payments.all()
    
    # Check if return exists
    try:
        return_obj = sale.returns.first()
    except Return.DoesNotExist:
        return_obj = None
    
    return render(request, 'sales/detail.html', {
        'sale': sale,
        'items': items,
        'payments': payments,
        'return_obj': return_obj,
        'title': f'Sale #{sale.sale_number}',
    })

@login_required
@business_required
def sale_update_view(request, sale_id):
    """Update a sale."""
    sale = get_object_or_404(Sale, id=sale_id, business=request.user.business)
    business = request.user.business
    
    # Don't allow editing if payment is completed
    if sale.payment_status == 'PAID':
        messages.warning(request, 'This sale has been paid and cannot be edited.')
        return redirect('sales:detail', sale_id=sale.id)
    
    if request.method == 'POST':
        form = SaleForm(request.POST, instance=sale, business=business)
        formset = SaleItemFormSet(request.POST, instance=sale, business=business)
        
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                # Update sale
                sale = form.save()
                
                # Update stock for changed items
                for item_form in formset:
                    if item_form.cleaned_data:
                        product = item_form.cleaned_data.get('product')
                        if product:
                            # Get original quantity if updating existing item
                            if item_form.instance.pk:
                                original_qty = item_form.instance.quantity
                                new_qty = item_form.cleaned_data['quantity']
                                diff = new_qty - original_qty
                                product.current_stock -= diff
                                product.save()
                
                formset.save()
                
                messages.success(request, f'Sale #{sale.sale_number} updated successfully!')
                return redirect('sales:detail', sale_id=sale.id)
    else:
        form = SaleForm(instance=sale, business=business)
        formset = SaleItemFormSet(instance=sale, business=business)
    
    return render(request, 'sales/form.html', {
        'form': form,
        'formset': formset,
        'sale': sale,
        'title': f'Edit Sale #{sale.sale_number}',
    })

@login_required
@business_required
@require_POST
def sale_delete_view(request, sale_id):
    """Delete a sale (only if not paid)."""
    sale = get_object_or_404(Sale, id=sale_id, business=request.user.business)
    
    if sale.payment_status == 'PAID':
        messages.error(request, 'Cannot delete a paid sale.')
        return redirect('sales:detail', sale_id=sale.id)
    
    with transaction.atomic():
        # Restore stock
        for item in sale.sale_items.all():
            product = item.product
            product.current_stock += item.quantity
            product.save()
        
        sale_number = sale.sale_number
        sale.delete()
        
        messages.success(request, f'Sale #{sale_number} deleted successfully!')
        return redirect('sales:list')

# === Payment Views ===

@login_required
@business_required
def payment_create_view(request, sale_id):
    """Process a payment for a sale."""
    sale = get_object_or_404(Sale, id=sale_id, business=request.user.business)
    
    if sale.payment_status == 'PAID':
        messages.warning(request, 'This sale is already fully paid.')
        return redirect('sales:detail', sale_id=sale.id)
    
    if request.method == 'POST':
        form = PaymentForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                payment = form.save(commit=False)
                payment.sale = sale
                payment.business = request.user.business
                payment.created_by = request.user
                payment.payment_status = 'COMPLETED'
                payment.save()
                
                # Update sale payment details
                sale.amount_paid += payment.amount
                sale.save()
                
                # Log activity
                UserActivity.objects.create(
                    user=request.user,
                    action='CREATE',
                    model_name='Payment',
                    object_id=str(payment.id),
                    changes={'amount': float(payment.amount), 'method': payment.payment_method},
                    business=request.user.business,
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', '')
                )
                
                messages.success(request, f'Payment of KSh {payment.amount:,.2f} received successfully!')
                return redirect('sales:detail', sale_id=sale.id)
    else:
        form = PaymentForm()
    
    return render(request, 'sales/payment.html', {
        'form': form,
        'sale': sale,
        'title': f'Process Payment - Sale #{sale.sale_number}',
    })

@login_required
@business_required
def payment_receipt_view(request, payment_id):
    """View and print payment receipt."""
    payment = get_object_or_404(Payment, id=payment_id, business=request.user.business)
    sale = payment.sale
    
    return render(request, 'sales/receipt.html', {
        'payment': payment,
        'sale': sale,
        'business': request.user.business,
        'title': f'Receipt - {payment.payment_number}',
    })

# === Return Views ===

@login_required
@business_required
def return_create_view(request, sale_id):
    """Process a return for a sale."""
    sale = get_object_or_404(Sale, id=sale_id, business=request.user.business)
    
    if request.method == 'POST':
        form = ReturnForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                return_obj = form.save(commit=False)
                return_obj.sale = sale
                return_obj.business = request.user.business
                return_obj.created_by = request.user
                return_obj.save()
                
                # Update stock
                items_data = return_obj.items
                for product_id, quantity in items_data.items():
                    try:
                        product = Product.objects.get(id=product_id, business=request.user.business)
                        product.current_stock += quantity
                        product.save()
                    except Product.DoesNotExist:
                        pass
                
                # Update sale total
                sale.total -= return_obj.refund_amount
                sale.save()
                
                messages.success(request, f'Return #{return_obj.return_number} processed successfully!')
                return redirect('sales:detail', sale_id=sale.id)
    else:
        # Pre-populate with sale items
        initial_items = {}
        for item in sale.sale_items.all():
            initial_items[str(item.product.id)] = item.quantity
        form = ReturnForm(initial={'items': json.dumps(initial_items)})
    
    return render(request, 'sales/return_form.html', {
        'form': form,
        'sale': sale,
        'title': f'Process Return - Sale #{sale.sale_number}',
    })

# === API Views ===

@login_required
@business_required
def get_sale_stats(request):
    """Get sales statistics for dashboard."""
    business = request.user.business
    today = timezone.now().date()
    
    # Today's stats
    today_sales = Sale.objects.filter(business=business, sale_date__date=today)
    
    # This week
    week_start = today - timedelta(days=today.weekday())
    week_sales = Sale.objects.filter(business=business, sale_date__date__gte=week_start)
    
    # This month
    month_start = today.replace(day=1)
    month_sales = Sale.objects.filter(business=business, sale_date__date__gte=month_start)
    
    data = {
        'today': {
            'count': today_sales.count(),
            'revenue': today_sales.aggregate(total=Sum('total'))['total'] or 0,
        },
        'week': {
            'count': week_sales.count(),
            'revenue': week_sales.aggregate(total=Sum('total'))['total'] or 0,
        },
        'month': {
            'count': month_sales.count(),
            'revenue': month_sales.aggregate(total=Sum('total'))['total'] or 0,
        },
        'top_products': list(
            SaleItem.objects.filter(
                sale__business=business,
                sale__sale_date__date__gte=month_start
            ).values('product__name').annotate(
                total_sold=Sum('quantity'),
                total_revenue=Sum('total')
            ).order_by('-total_sold')[:10]
        ),
        'payment_methods': list(
            Sale.objects.filter(business=business).values('payment_method').annotate(
                count=Count('id'),
                total=Sum('total')
            ).order_by('-total')
        ),
    }
    
    return JsonResponse(data)

@login_required
@business_required
def get_sale_by_invoice(request):
    """Get sale details by invoice number."""
    invoice = request.GET.get('invoice')
    if not invoice:
        return JsonResponse({'error': 'Invoice number required'}, status=400)
    
    try:
        sale = Sale.objects.get(sale_number=invoice, business=request.user.business)
        items = sale.sale_items.values(
            'product__name', 'quantity', 'unit_price', 'total'
        )
        
        return JsonResponse({
            'id': str(sale.id),
            'sale_number': sale.sale_number,
            'customer_name': sale.customer_name,
            'customer_phone': sale.customer_phone,
            'total': float(sale.total),
            'payment_status': sale.payment_status,
            'items': list(items),
        })
    except Sale.DoesNotExist:
        return JsonResponse({'error': 'Sale not found'}, status=404)

@login_required
@business_required
def export_sales_csv(request):
    """Export sales to CSV."""
    business = request.user.business
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    sales = Sale.objects.filter(business=business)
    
    if date_from:
        sales = sales.filter(sale_date__date__gte=date_from)
    if date_to:
        sales = sales.filter(sale_date__date__lte=date_to)
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="sales_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Invoice #', 'Date', 'Customer', 'Phone', 'Subtotal', 'Tax', 
        'Discount', 'Total', 'Payment Method', 'Payment Status'
    ])
    
    for sale in sales:
        writer.writerow([
            sale.sale_number,
            sale.sale_date.strftime('%Y-%m-%d %H:%M'),
            sale.customer_name,
            sale.customer_phone,
            float(sale.subtotal),
            float(sale.tax),
            float(sale.discount),
            float(sale.total),
            sale.payment_method,
            sale.payment_status,
        ])
    
    return response