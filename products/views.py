from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.db import models
from django.db.models import Q, Sum, Count
from django.views.decorators.http import require_POST
from django.utils import timezone
import csv
import io
import json

from .models import Product, Category, ProductVariant, ProductImage
from .forms import ProductForm, CategoryForm, ProductSearchForm, ProductBulkUploadForm
from accounts.models import UserActivity
from accounts.decorators import business_required, role_required

# === Category Views ===

@login_required
@business_required
def category_list_view(request):
    """List all product categories."""
    categories = Category.objects.filter(
        business=request.user.business,
        parent__isnull=True
    ).prefetch_related('subcategories')
    
    return render(request, 'products/categories.html', {
        'categories': categories,
        'title': 'Categories'
    })

@login_required
@business_required
def category_create_view(request):
    """Create a new category."""
    if request.method == 'POST':
        form = CategoryForm(request.POST, business=request.user.business)
        if form.is_valid():
            category = form.save(commit=False)
            category.business = request.user.business
            category.save()
            
            UserActivity.objects.create(
                user=request.user,
                action='CREATE',
                model_name='Category',
                object_id=str(category.id),
                changes={'name': category.name},
                business=request.user.business,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            messages.success(request, f'Category "{category.name}" created successfully!')
            return redirect('products:categories')
    else:
        form = CategoryForm(business=request.user.business)
    
    return render(request, 'products/category_form.html', {
        'form': form,
        'title': 'Create Category'
    })

@login_required
@business_required
def category_update_view(request, category_id):
    """Update a category."""
    category = get_object_or_404(Category, id=category_id, business=request.user.business)
    
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, f'Category "{category.name}" updated successfully!')
            return redirect('products:categories')
    else:
        form = CategoryForm(instance=category)
    
    return render(request, 'products/category_form.html', {
        'form': form,
        'category': category,
        'title': 'Edit Category'
    })

@login_required
@business_required
@require_POST
def category_delete_view(request, category_id):
    """Delete a category."""
    category = get_object_or_404(Category, id=category_id, business=request.user.business)
    
    if category.products.exists():
        messages.error(request, f'Cannot delete "{category.name}" because it has products. Move or delete the products first.')
        return redirect('products:categories')
    
    category_name = category.name
    category.delete()
    messages.success(request, f'Category "{category_name}" deleted successfully!')
    return redirect('products:categories')

# === Product Views ===

@login_required
@business_required
def product_list_view(request):
    """List all products with search and filters."""
    business = request.user.business
    products = Product.objects.filter(business=business)
    
    # Search form
    form = ProductSearchForm(request.GET or None, business=business)
    
    if form.is_valid():
        # Search by name, sku, barcode
        search = form.cleaned_data.get('search')
        if search:
            products = products.filter(
                Q(name__icontains=search) |
                Q(sku__icontains=search) |
                Q(barcode__icontains=search) |
                Q(supplier_name__icontains=search)
            )
        
        # Filter by category
        category = form.cleaned_data.get('category')
        if category:
            products = products.filter(category=category)
        
        # Filter by status
        status = form.cleaned_data.get('status')
        if status:
            products = products.filter(status=status)
        
        # Filter low stock
        low_stock = form.cleaned_data.get('low_stock')
        if low_stock:
            products = products.filter(current_stock__lte=models.F('reorder_level'))
        
        # Sort
        sort_by = form.cleaned_data.get('sort_by')
        if sort_by:
            products = products.order_by(sort_by)
        else:
            products = products.order_by('name')
    
    # Pagination
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Summary stats
    total_products = products.count()
    low_stock_count = products.filter(current_stock__lte=models.F('reorder_level')).count()
    out_of_stock_count = products.filter(current_stock=0).count()
    total_stock_value = products.aggregate(
        total=Sum(models.F('current_stock') * models.F('purchase_price'))
    )['total'] or 0
    
    return render(request, 'products/list.html', {
        'page_obj': page_obj,
        'form': form,
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'total_stock_value': total_stock_value,
        'title': 'Products'
    })

@login_required
@business_required
def product_create_view(request):
    """Create a new product."""
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, business=request.user.business)
        if form.is_valid():
            product = form.save(commit=False)
            product.business = request.user.business
            product.created_by = request.user
            product.save()
            
            # Handle additional images if any
            # (This would be handled by a separate view)
            
            UserActivity.objects.create(
                user=request.user,
                action='CREATE',
                model_name='Product',
                object_id=str(product.id),
                changes={'name': product.name, 'sku': product.sku},
                business=request.user.business,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            messages.success(request, f'Product "{product.name}" created successfully!')
            return redirect('products:detail', product_id=product.id)
    else:
        form = ProductForm(business=request.user.business)
    
    return render(request, 'products/form.html', {
        'form': form,
        'title': 'Add Product'
    })

@login_required
@business_required
def product_detail_view(request, product_id):
    """View product details."""
    product = get_object_or_404(Product, id=product_id, business=request.user.business)
    
    # Get variants
    variants = product.variants.filter(is_active=True)
    
    # Get images
    images = product.images.all()
    
    # Get recent sales (would need sales module)
    # recent_sales = SaleItem.objects.filter(product=product).order_by('-sale__created_at')[:10]
    
    return render(request, 'products/detail.html', {
        'product': product,
        'variants': variants,
        'images': images,
        'title': product.name
    })

@login_required
@business_required
def product_update_view(request, product_id):
    """Update a product."""
    product = get_object_or_404(Product, id=product_id, business=request.user.business)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product, business=request.user.business)
        if form.is_valid():
            form.save()
            
            UserActivity.objects.create(
                user=request.user,
                action='UPDATE',
                model_name='Product',
                object_id=str(product.id),
                changes={'updated': product.name},
                business=request.user.business,
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            messages.success(request, f'Product "{product.name}" updated successfully!')
            return redirect('products:detail', product_id=product.id)
    else:
        form = ProductForm(instance=product, business=request.user.business)
    
    return render(request, 'products/form.html', {
        'form': form,
        'product': product,
        'title': 'Edit Product'
    })

@login_required
@business_required
@require_POST
def product_delete_view(request, product_id):
    """Delete a product."""
    product = get_object_or_404(Product, id=product_id, business=request.user.business)
    
    # Check if product has sales
    from sales.models import SaleItem
    if SaleItem.objects.filter(product=product).exists():
        messages.error(
            request,
            f'Cannot delete "{product.name}" because it has sales records. Consider marking it as discontinued instead.'
        )
        return redirect('products:detail', product_id=product.id)
    
    product_name = product.name
    product.delete()
    messages.success(request, f'Product "{product_name}" deleted successfully!')
    return redirect('products:list')

@login_required
@business_required
def product_bulk_upload_view(request):
    """Bulk upload products via CSV."""
    if request.method == 'POST':
        form = ProductBulkUploadForm(request.POST, request.FILES)
        if form.is_valid():
            csv_file = request.FILES['csv_file']
            csv_data = csv_file.read().decode('utf-8')
            io_string = io.StringIO(csv_data)
            
            created_count = 0
            errors = []
            
            for row_num, row in enumerate(csv.DictReader(io_string), start=2):
                try:
                    # Basic validation and cleanup
                    name = row.get('name', '').strip()
                    if not name:
                        errors.append(f"Row {row_num}: Product name is required")
                        continue
                    
                    # Check if product exists by SKU
                    sku = row.get('sku', '').strip()
                    if Product.objects.filter(business=request.user.business, sku=sku).exists():
                        errors.append(f"Row {row_num}: Product with SKU '{sku}' already exists")
                        continue
                    
                    # Get category
                    category_name = row.get('category', '').strip()
                    category = None
                    if category_name:
                        category, _ = Category.objects.get_or_create(
                            business=request.user.business,
                            name=category_name,
                        )
                    
                    # Create product
                    product = Product(
                        business=request.user.business,
                        name=name,
                        sku=sku or f"CSV{timezone.now().strftime('%Y%m%d%H%M%S')}{row_num}",
                        barcode=row.get('barcode', '').strip(),
                        category=category,
                        purchase_price=float(row.get('purchase_price', 0) or 0),
                        selling_price=float(row.get('selling_price', 0) or 0),
                        current_stock=int(row.get('current_stock', 0) or 0),
                        reorder_level=int(row.get('reorder_level', 5) or 5),
                        unit=row.get('unit', 'PCS').strip() or 'PCS',
                        supplier_name=row.get('supplier_name', '').strip(),
                        description=row.get('description', '').strip(),
                        created_by=request.user,
                    )
                    product.save()
                    created_count += 1
                    
                except Exception as e:
                    errors.append(f"Row {row_num}: {str(e)}")
            
            if created_count > 0:
                messages.success(request, f'Successfully imported {created_count} products!')
            
            if errors:
                for error in errors[:5]:  # Show first 5 errors
                    messages.warning(request, error)
                if len(errors) > 5:
                    messages.warning(request, f'And {len(errors) - 5} more errors...')
            
            return redirect('products:list')
    else:
        form = ProductBulkUploadForm()
    
    return render(request, 'products/bulk_upload.html', {
        'form': form,
        'title': 'Bulk Upload Products'
    })

@login_required
@business_required
def product_export_view(request):
    """Export products to CSV."""
    products = Product.objects.filter(business=request.user.business)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="products_{timezone.now().strftime("%Y%m%d")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'name', 'sku', 'barcode', 'category', 'purchase_price', 'selling_price',
        'current_stock', 'unit', 'reorder_level', 'supplier_name', 'description'
    ])
    
    for product in products:
        writer.writerow([
            product.name,
            product.sku,
            product.barcode or '',
            product.category.name if product.category else '',
            product.purchase_price,
            product.selling_price,
            product.current_stock,
            product.unit,
            product.reorder_level,
            product.supplier_name,
            product.description
        ])
    
    return response

# === API Views (JSON responses for AJAX) ===

@login_required
@business_required
def get_product_by_barcode(request):
    """Get product details by barcode (for POS)."""
    barcode = request.GET.get('barcode')
    if not barcode:
        return JsonResponse({'error': 'Barcode required'}, status=400)
    
    try:
        product = Product.objects.get(
            business=request.user.business,
            barcode=barcode,
            is_active=True
        )
        return JsonResponse({
            'id': str(product.id),
            'name': product.name,
            'sku': product.sku,
            'selling_price': float(product.selling_price),
            'current_stock': product.current_stock,
            'unit': product.unit
        })
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)

@login_required
@business_required
def update_stock(request):
    """Update product stock via AJAX."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    product_id = request.POST.get('product_id')
    quantity = int(request.POST.get('quantity', 0))
    action = request.POST.get('action', 'set')  # 'set', 'add', 'subtract'
    
    if not product_id:
        return JsonResponse({'error': 'Product ID required'}, status=400)
    
    try:
        product = Product.objects.get(id=product_id, business=request.user.business)
        
        if action == 'set':
            product.current_stock = quantity
        elif action == 'add':
            product.current_stock += quantity
        elif action == 'subtract':
            product.current_stock = max(0, product.current_stock - quantity)
        else:
            return JsonResponse({'error': 'Invalid action'}, status=400)
        
        product.save()
        
        return JsonResponse({
            'success': True,
            'current_stock': product.current_stock,
            'is_low_stock': product.is_low_stock
        })
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)
