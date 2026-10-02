from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse, JsonResponse
from django.db import models, transaction
from django.db.models import F, Q, Sum, Count
from django.views.decorators.http import require_POST
from django.utils import timezone
import csv
import io
import json
from datetime import timedelta

from .models import Product, Category, ProductVariant, ProductImage
from .forms import ProductForm, CategoryForm, ProductSearchForm, ProductBulkUploadForm
from accounts.models import UserActivity
from accounts.decorators import business_required, permission_required, role_required
from barber.models import Appointment, BarberService
from sales.models import SaleItem
from accounts.models import User

# === Category Views ===

@login_required
@business_required
@permission_required('manage_products')
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
@permission_required('manage_products')
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
@permission_required('manage_products')
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
@permission_required('manage_products')
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
@permission_required('manage_products')
def product_list_view(request):
    """List all products with search and filters."""
    business = request.user.business
    if business.business_type == "SALON":
        retail_filter = Q(metadata__salon_service__isnull=True) | Q(metadata__salon_service=False)
        products = Product.objects.filter(
            retail_filter,
            business=business,
        ).select_related("category")
        search_form = ProductSearchForm(request.GET or None, business=business)
        stock_filter = request.GET.get("stock", "")
        if search_form.is_valid():
            search = search_form.cleaned_data.get("search")
            if search:
                products = products.filter(
                    Q(name__icontains=search)
                    | Q(sku__icontains=search)
                    | Q(barcode__icontains=search)
                    | Q(supplier_name__icontains=search)
                )
            category = search_form.cleaned_data.get("category")
            if category:
                products = products.filter(category=category)
            status = search_form.cleaned_data.get("status")
            if status:
                products = products.filter(status=status)
            sort_by = search_form.cleaned_data.get("sort_by")
            products = products.order_by(sort_by or "name")
        if stock_filter == "low":
            products = products.filter(current_stock__gt=0, current_stock__lte=F("reorder_level"))
        elif stock_filter == "out":
            products = products.filter(current_stock=0)
        elif stock_filter == "healthy":
            products = products.filter(current_stock__gt=F("reorder_level"))

        retail_products = Product.objects.filter(retail_filter, business=business)
        active_retail = retail_products.filter(is_active=True)
        paginator = Paginator(products, 24)
        page_obj = paginator.get_page(request.GET.get("page"))
        query_params = request.GET.copy()
        query_params.pop("page", None)
        return render(request, "salon/products.html", {
            "page": "products",
            "page_obj": page_obj,
            "form": search_form,
            "stock_filter": stock_filter,
            "product_count": retail_products.count(),
            "active_count": active_retail.count(),
            "low_stock_count": active_retail.filter(
                current_stock__gt=0,
                current_stock__lte=F("reorder_level"),
            ).count(),
            "out_of_stock_count": active_retail.filter(current_stock=0).count(),
            "total_stock_value": active_retail.aggregate(
                total=Sum(F("current_stock") * F("purchase_price")),
            )["total"] or 0,
            "querystring": query_params.urlencode(),
            "title": "Retail products",
        })

    if business.business_type == "ELECTRONICS":
        form = ProductSearchForm(request.GET or None, business=business)
        stock_filter = request.GET.get("stock", "")
        supplier_filter = request.GET.get("supplier", "").strip()
        products = Product.objects.filter(business=business).select_related("category")
        if form.is_valid():
            search = form.cleaned_data.get("search")
            if search:
                products = products.filter(
                    Q(name__icontains=search)
                    | Q(sku__icontains=search)
                    | Q(barcode__icontains=search)
                    | Q(supplier_name__icontains=search)
                )
            if form.cleaned_data.get("category"):
                products = products.filter(category=form.cleaned_data["category"])
            if form.cleaned_data.get("status"):
                products = products.filter(status=form.cleaned_data["status"])
            if form.cleaned_data.get("low_stock"):
                products = products.filter(current_stock__gt=0, current_stock__lte=F("reorder_level"))
            products = products.order_by(form.cleaned_data.get("sort_by") or "name")
        if supplier_filter:
            products = products.filter(supplier_name__icontains=supplier_filter)
        if stock_filter == "low":
            products = products.filter(current_stock__gt=0, current_stock__lte=F("reorder_level"))
        elif stock_filter == "out":
            products = products.filter(current_stock=0)
        elif stock_filter == "healthy":
            products = products.filter(current_stock__gt=F("reorder_level"))

        active_products = Product.objects.filter(business=business, is_active=True)
        product_count = active_products.count()
        query_params = request.GET.copy()
        query_params.pop("page", None)
        return render(request, "electronics/products.html", {
            "page_obj": Paginator(products, 25).get_page(request.GET.get("page")),
            "form": form,
            "categories": Category.objects.filter(
                business=business, is_active=True
            ).annotate(product_count=Count("products", filter=Q(products__is_active=True))),
            "product_count": product_count,
            "category_count": active_products.values("category_id").distinct().count(),
            "active_count": product_count,
            "low_stock_count": active_products.filter(
                current_stock__gt=0, current_stock__lte=F("reorder_level")
            ).count(),
            "out_of_stock_count": active_products.filter(current_stock=0).count(),
            "total_stock_value": active_products.aggregate(
                total=Sum(F("current_stock") * F("purchase_price"))
            )["total"] or 0,
            "stock_filter": stock_filter,
            "supplier_filter": supplier_filter,
            "querystring": query_params.urlencode(),
            "title": "Products",
        })

    if business.business_type == "BARBER":
        editing_product_id = request.POST.get("product_id", "")
        editing_product = None
        if editing_product_id:
            editing_product = get_object_or_404(Product, id=editing_product_id, business=business)
        form = ProductForm(
            request.POST or None,
            request.FILES or None,
            instance=editing_product,
            business=business,
        )
        if request.method == "POST":
            if form.is_valid():
                product = form.save(commit=False)
                product.business = business
                if not product.pk:
                    product.created_by = request.user
                product.save()
                UserActivity.objects.create(
                    user=request.user,
                    action="UPDATE" if editing_product else "CREATE",
                    model_name="Product",
                    object_id=str(product.id),
                    changes={"name": product.name, "sku": product.sku},
                    business=business,
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )
                messages.success(
                    request,
                    f'Product "{product.name}" {"updated" if editing_product else "created"} successfully!',
                )
                return redirect("products:list")
        payload = _barber_product_data(request)
        return render(request, "products/barber_list.html", {
            "title": "Products",
            "form": form,
            "product_data": payload,
            "editing_product_id": editing_product_id,
            "categories": Category.objects.filter(business=business, is_active=True),
        })

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


def _barber_product_data(request):
    business = request.user.business
    cutoff = timezone.now() - timedelta(days=30)
    service_names = BarberService.objects.filter(
        business=business,
    ).values_list("name", flat=True)
    products = Product.objects.filter(business=business).exclude(name__in=service_names)
    active_products = products.filter(is_active=True)
    search = request.GET.get("search", "").strip()
    category_id = request.GET.get("category", "").strip()
    status_filter = request.GET.get("status", "").strip()
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(sku__icontains=search) |
            Q(barcode__icontains=search) |
            Q(supplier_name__icontains=search)
        )
    if category_id:
        products = products.filter(category_id=category_id)
    if status_filter == "LOW":
        products = products.filter(is_active=True, current_stock__gt=0, current_stock__lte=F("reorder_level"))
    elif status_filter == "OUT":
        products = products.filter(is_active=True, current_stock=0)
    elif status_filter == "ARCHIVED":
        products = products.filter(is_active=False)
    else:
        products = products.filter(is_active=True)

    paid_items = SaleItem.objects.filter(
        product__in=active_products,
        sale__business=business,
        sale__sale_date__gte=cutoff,
        sale__payment_status="PAID",
    )
    sales_totals = paid_items.aggregate(
        units=Sum("quantity"),
        revenue=Sum("total"),
        cost=Sum(F("cost_price") * F("quantity")),
    )
    revenue = sales_totals["revenue"] or 0
    cost = sales_totals["cost"] or 0
    margin = ((revenue - cost) / revenue * 100) if revenue else 0

    completed_appointments = Appointment.objects.filter(
        business=business,
        status="DONE",
        completed_at__gte=cutoff,
    )
    appointments_count = completed_appointments.count()
    attached_appointments = completed_appointments.filter(
        sale__sale_items__product__in=active_products,
        sale__payment_status="PAID",
    ).distinct()
    attached_count = attached_appointments.count()
    attach_rate = attached_count / appointments_count * 100 if appointments_count else 0

    barber_rates = []
    barbers = User.objects.filter(business=business, role="BARBER", is_active=True).order_by("first_name", "last_name")
    for barber in barbers:
        barber_visits = completed_appointments.filter(barber=barber)
        visit_count = barber_visits.count()
        attached_count_for_barber = barber_visits.filter(
            sale__sale_items__product__in=active_products,
            sale__payment_status="PAID",
        ).distinct().count()
        barber_rates.append({
            "name": barber.get_full_name() or barber.email,
            "rate": round(attached_count_for_barber / visit_count * 100) if visit_count else 0,
            "visits": visit_count,
        })

    product_rows = products.select_related("category").annotate(
        sold_30d=Sum(
            "sale_items__quantity",
            filter=Q(
                sale_items__sale__sale_date__gte=cutoff,
                sale_items__sale__payment_status="PAID",
            ),
        ),
        profit_30d=Sum(
            F("sale_items__total") - F("sale_items__cost_price") * F("sale_items__quantity"),
            filter=Q(
                sale_items__sale__sale_date__gte=cutoff,
                sale_items__sale__payment_status="PAID",
            ),
        ),
        revenue_30d=Sum(
            "sale_items__total",
            filter=Q(
                sale_items__sale__sale_date__gte=cutoff,
                sale_items__sale__payment_status="PAID",
            ),
        ),
    ).order_by("name")
    rows = [{
        "id": str(product.id),
        "name": product.name,
        "sku": product.sku,
        "category": product.category.name if product.category_id else "Uncategorized",
        "category_id": str(product.category_id) if product.category_id else "",
        "stock": product.current_stock,
        "reorder": product.reorder_level,
        "cost": float(product.purchase_price),
        "price": float(product.selling_price),
        "margin": round(product.profit_margin),
        "sold_30d": product.sold_30d or 0,
        "profit_30d": float(product.profit_30d or 0),
        "revenue_30d": float(product.revenue_30d or 0),
        "active": product.is_active,
        "state": "archived" if not product.is_active else (
            "out" if product.current_stock <= 0 else (
                "low" if product.current_stock <= product.reorder_level else "healthy"
            )
        ),
        "detail_url": product.get_absolute_url(),
    } for product in product_rows]
    low_stock = [{
        "id": str(product.id),
        "name": product.name,
        "stock": product.current_stock,
        "reorder": product.reorder_level,
        "state": "out" if product.current_stock <= 0 else "low",
    } for product in active_products.filter(current_stock__lte=F("reorder_level")).order_by("current_stock", "name")]
    return {
        "products": rows,
        "metrics": {
            "revenue": float(revenue),
            "units": sales_totals["units"] or 0,
            "margin": round(margin),
            "attach_rate": round(attach_rate),
            "attach_count": attached_count,
            "appointment_count": appointments_count,
            "total_products": active_products.count(),
            "low_stock_count": len(low_stock),
            "out_of_stock_count": active_products.filter(current_stock=0).count(),
        },
        "low_stock": low_stock,
        "barber_rates": barber_rates,
        "last_updated": timezone.localtime().isoformat(),
    }


@login_required
@business_required
@permission_required("manage_products")
def live_barber_products(request):
    if request.user.business.business_type != "BARBER":
        return JsonResponse({"error": "This live view is only available to barbershops."}, status=404)
    return JsonResponse(_barber_product_data(request))


@require_POST
@login_required
@business_required
@permission_required("manage_products")
def barber_product_action(request, product_id):
    if request.user.business.business_type != "BARBER":
        return JsonResponse({"error": "This action is only available to barbershops."}, status=404)
    action = request.POST.get("action", "")
    try:
        with transaction.atomic():
            product = Product.objects.select_for_update().get(
                id=product_id,
                business=request.user.business,
            )
            if action == "restock":
                try:
                    quantity = int(request.POST.get("quantity", ""))
                except (TypeError, ValueError):
                    return JsonResponse({"error": "Enter a whole number of units to restock."}, status=400)
                if quantity <= 0:
                    return JsonResponse({"error": "Restock quantity must be greater than zero."}, status=400)
                product.current_stock += quantity
                product.save(update_fields=["current_stock", "status", "updated_at"])
            elif action == "archive":
                product.is_active = False
                product.save(update_fields=["is_active", "updated_at"])
                Product.objects.filter(pk=product.pk).update(status="INACTIVE")
            else:
                return JsonResponse({"error": "Choose a valid product action."}, status=400)
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found."}, status=404)
    return JsonResponse({"success": True})

@login_required
@business_required
@permission_required('manage_products')
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
@permission_required('manage_products')
def product_detail_view(request, product_id):
    """View product details."""
    product = get_object_or_404(Product, id=product_id, business=request.user.business)
    
    # Get variants
    variants = product.variants.filter(is_active=True)
    
    # Get images
    images = product.images.all()
    
    recent_sales = SaleItem.objects.filter(
        product=product,
        sale__business=request.user.business,
    ).select_related("sale", "sale__customer").order_by("-sale__sale_date")[:10]
    thirty_days_ago = timezone.now() - timedelta(days=30)
    sales_summary = SaleItem.objects.filter(
        product=product,
        sale__business=request.user.business,
        sale__sale_date__gte=thirty_days_ago,
    ).aggregate(units=Sum("quantity"), revenue=Sum("total"))

    return render(request, (
        "electronics/product_detail.html"
        if request.user.business.business_type == "ELECTRONICS"
        else "products/detail.html"
    ), {
        'product': product,
        'variants': variants,
        'images': images,
        "recent_sales": recent_sales,
        "sales_summary": sales_summary,
        "unit_margin": product.selling_price - product.purchase_price,
        "margin_percent": (
            (product.selling_price - product.purchase_price) / product.selling_price * 100
            if product.selling_price else 0
        ),
        'title': product.name
    })

@login_required
@business_required
@permission_required('manage_products')
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
@permission_required('manage_products')
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
@permission_required('manage_products')
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
@permission_required('manage_products')
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
@permission_required('manage_products')
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
@permission_required('manage_products')
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
